"""Bounded persistent Python and Node.js REPL worker sessions with security sandbox."""
from __future__ import annotations

import ast
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field

from core import outcome

# Safe builtins whitelist - only safe functions and types
_SAFE_BUILTINS = {
    # Types
    'bool': bool, 'int': int, 'float': float, 'str': str, 'bytes': bytes,
    'list': list, 'tuple': tuple, 'dict': dict, 'set': set, 'frozenset': frozenset,
    'complex': complex, 'range': range, 'slice': slice,
    # Safe functions
    'abs': abs, 'all': all, 'any': any, 'bin': bin, 'hex': hex, 'oct': oct,
    'chr': chr, 'ord': ord, 'len': len, 'max': max, 'min': min, 'sum': sum,
    'sorted': sorted, 'reversed': reversed, 'enumerate': enumerate, 'zip': zip,
    'filter': filter, 'map': map, 'round': round, 'pow': pow,
    'divmod': divmod, 'hash': hash, 'id': id, 'isinstance': isinstance,
    'issubclass': issubclass, 'type': type, 'repr': repr, 'ascii': ascii,
    'format': format, 'str': str, 'bytes': bytes, 'bytearray': bytearray,
    # Math
    'math': __import__('math'),
    # String
    'str': str,
}

# Blocked AST node types
_BLOCKED_NODES = {
    ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
    ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef,
    ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.Await, ast.Yield, ast.YieldFrom,
    ast.Raise, ast.Try, ast.With, ast.AsyncWith,
    ast.Assert, ast.Break, ast.Continue,
    ast.Delete, ast.Assign, ast.AugAssign, ast.AnnAssign,
}

# Blocked attribute names
_BLOCKED_ATTRS = {
    '__import__', '__builtins__', '__loader__', '__spec__',
    '__code__', '__globals__', '__locals__', '__closure__',
    '__func__', '__self__', '__class__', '__bases__',
    '__subclasses__', '__mro__', '__dict__', '__doc__',
    '__module__', '__package__', '__file__', '__cached__',
    '__builtins__', 'eval', 'exec', 'compile', 'open',
    'input', 'breakpoint', 'globals', 'locals', 'vars',
    'dir', 'getattr', 'setattr', 'delattr', 'hasattr',
}


def _validate_ast(node: ast.AST) -> bool:
    """Recursively validate AST to ensure no dangerous operations."""
    if isinstance(node, _BLOCKED_NODES):
        return False
    
    # Check for attribute access to blocked names
    if isinstance(node, ast.Attribute):
        if node.attr in _BLOCKED_ATTRS:
            return False
    
    # Check for name access to blocked names
    if isinstance(node, ast.Name):
        if node.id in _BLOCKED_ATTRS:
            return False
    
    # Recursively check all child nodes
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    if not _validate_ast(item):
                        return False
        elif isinstance(value, ast.AST):
            if not _validate_ast(value):
                return False
    
    return True


_PY_WORKER = r'''import ast, contextlib, io, json, sys, traceback

# Security sandbox configuration
_SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "bool": bool, "int": int, "float": float, "str": str, "bytes": bytes,
    "list": list, "tuple": tuple, "dict": dict, "set": set,
    "abs": abs, "all": all, "any": any, "len": len, "max": max, "min": min,
    "sum": sum, "sorted": sorted, "reversed": reversed, "range": range,
    "enumerate": enumerate, "zip": zip, "chr": chr, "ord": ord,
    "round": round, "pow": pow, "divmod": divmod,
}

_BLOCKED_NODES = ("Import", "ImportFrom", "Global", "Nonlocal", "FunctionDef",
                  "ClassDef", "Lambda", "ListComp", "SetComp", "DictComp",
                  "GeneratorExp", "Raise", "Try", "With", "Assert", "Break",
                  "Continue", "Delete", "Assign", "AugAssign", "AnnAssign")

def _validate_ast(node):
    if node.__class__.__name__ in _BLOCKED_NODES:
        return False
    if isinstance(node, ast.Attribute):
        blocked = {"__builtins__", "__import__", "eval", "exec", "compile", "open",
                  "input", "breakpoint", "globals", "locals", "vars", "dir",
                  "getattr", "setattr", "delattr", "hasattr"}
        if node.attr in blocked:
            return False
    if isinstance(node, ast.Name):
        if node.id in blocked:
            return False
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, ast.AST):
                    if not _validate_ast(item):
                        return False
        elif isinstance(value, ast.AST):
            if not _validate_ast(value):
                return False
    return True

namespace = {"__name__": "__jinx_repl__", "__builtins__": _SAFE_BUILTINS}

for line in sys.stdin:
    try:
        req = json.loads(line)
        output = io.StringIO()
        code = req.get("code", "")
        
        # Parse and validate AST first
        tree = ast.parse(code, "<jinx-repl>", "exec")
        if not _validate_ast(tree):
            raise ValueError("Code contains blocked operations")
        
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            if tree.body and isinstance(tree.body[-1], ast.Expr):
                final = ast.Expression(tree.body.pop().value)
                if tree.body:
                    exec(compile(tree, "<jinx-repl>", "exec"), namespace)
                value = eval(compile(final, "<jinx-repl>", "eval"), namespace)
                if value is not None:
                    print(repr(value))
            else:
                exec(compile(tree, "<jinx-repl>", "exec"), namespace)
        
        response = {"ok": True, "output": output.getvalue()}
    except BaseException as e:
        response = {"ok": False, "output": output.getvalue() if "output" in locals() else "", 
                   "error": str(e) if not isinstance(e, ValueError) or "blocked" not in str(e) else "Code contains blocked operations"}
    
    sys.__stdout__.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()
'''

_NODE_WORKER = r'''const readline=require('readline'), vm=require('vm');
const context=vm.createContext({console, Buffer, setTimeout, clearTimeout});
const rl=readline.createInterface({input:process.stdin, crlfDelay:Infinity});
rl.on('line', line=>{ let output=''; const old=console.log; console.log=(...a)=>output+=a.join(' ')+'\n';
 try { const value=vm.runInContext(JSON.parse(line).code, context, {timeout:30000}); if(value!==undefined) output+=String(value)+'\n'; process.stdout.write(JSON.stringify({ok:true,output})+'\n'); }
 catch(e){ process.stdout.write(JSON.stringify({ok:false,output,error:String(e)})+'\n'); }
 finally { console.log=old; }
});
'''

@dataclass
class _Session:
    id: str
    language: str
    process: subprocess.Popen
    lines: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        threading.Thread(target=self._read, daemon=True, name=f"jinx-repl-{self.id}").start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass

    def evaluate(self, code: str, timeout: float) -> dict:
        with self.lock:
            if self.process.poll() is not None:
                raise RuntimeError("REPL process exited")
            self.process.stdin.write(json.dumps({"code": code}, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            try:
                raw = self.lines.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError("evaluation timed out") from exc
            return json.loads(raw)


class ReplManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions: dict[str, _Session] = {}

    def start(self, language: str) -> str:
        language = str(language or "").lower()
        if language == "python":
            argv = [sys.executable, "-u", "-c", _PY_WORKER]
        elif language in {"javascript", "node", "js"}:
            node = shutil.which("node")
            if not node:
                raise RuntimeError("Node.js executable was not found")
            language, argv = "javascript", [node, "-e", _NODE_WORKER]
        else:
            raise ValueError("language must be python or javascript")
        with self._lock:
            if len(self._sessions) >= 8:
                raise RuntimeError("maximum of 8 REPL sessions reached")
            sid = uuid.uuid4().hex[:12]
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            # Security: shell=False is explicit (default), no command injection possible
            process = subprocess.Popen(
                argv, 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, 
                text=True, 
                encoding="utf-8",
                errors="replace", 
                bufsize=1, 
                creationflags=flags,
                shell=False  # Explicitly disable shell
            )
            self._sessions[sid] = _Session(sid, language, process)
            return sid

    def evaluate(self, sid: str, code: str, timeout: float = 30) -> str:
        with self._lock:
            session = self._sessions.get(str(sid))
        if session is None:
            return outcome.failed("repl_eval", "Unknown REPL session.")
        code = str(code or "")
        if not code.strip() or len(code) > 100_000:
            return outcome.failed("repl_eval", "Code is empty or exceeds 100,000 characters.")
        
        # Validate code before sending to worker
        try:
            tree = ast.parse(code, "<jinx-repl>", "exec")
            if not _validate_ast(tree):
                return outcome.failed("repl_eval", "Code contains blocked operations (import, exec, eval, etc.)")
        except SyntaxError as e:
            return outcome.failed("repl_eval", f"Syntax error: {e}")
        
        try:
            response = session.evaluate(code, max(1.0, min(float(timeout), 60.0)))
            return outcome.done("repl_eval", session_id=sid, language=session.language,
                                output=outcome.untrusted("repl-output", response.get("output", "")),
                                error=outcome.untrusted("repl-error", response.get("error", "")) or None,
                                verified=bool(response.get("ok")))
        except (TimeoutError, ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
            self.close(sid, force=True)
            return outcome.failed("repl_eval", str(exc), session_id=sid)

    def close(self, sid: str, force: bool = False) -> bool:
        with self._lock:
            session = self._sessions.pop(str(sid), None)
        if not session:
            return False
        proc = session.process
        if proc.poll() is None:
            proc.terminate() if force else proc.stdin.close()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
        return True

    def list(self) -> list[dict]:
        with self._lock:
            return [{"session_id": s.id, "language": s.language,
                     "running": s.process.poll() is None} for s in self._sessions.values()]


_DEFAULT = ReplManager()


def repl_polyglot(parameters: dict, **_context) -> str:
    p = parameters or {}
    action = str(p.get("action", "")).lower()
    sid = str(p.get("session_id", ""))
    try:
        if action == "start":
            sid = _DEFAULT.start(p.get("language", "python"))
            return outcome.done("repl_start", session_id=sid,
                                language=next(x["language"] for x in _DEFAULT.list() if x["session_id"] == sid))
        if action == "eval":
            return _DEFAULT.evaluate(sid, p.get("code", ""), p.get("timeout_seconds", 30))
        if action == "list":
            return outcome.done("repl_list", sessions=json.dumps(_DEFAULT.list()))
        if action == "close":
            return outcome.done("repl_close", session_id=sid) if _DEFAULT.close(sid) else outcome.failed("repl_close", "Unknown REPL session.")
        return outcome.failed("repl_polyglot", "Unsupported action.")
    except (OSError, ValueError, RuntimeError) as exc:
        return outcome.failed("repl_polyglot", str(exc))


TOOL = {"name": "repl_polyglot", "description": "Start persistent Python or JavaScript/Node REPL sessions, evaluate code while retaining variables, list and close sessions. Code runs as the current user in a child process.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["start", "eval", "list", "close"]},
            "language": {"type": "STRING", "enum": ["python", "javascript"]},
            "session_id": {"type": "STRING"}, "code": {"type": "STRING"},
            "timeout_seconds": {"type": "INTEGER"}}, "required": ["action"]},
        "handler": repl_polyglot, "tier": "extra", "brief": "Persistent Python/JavaScript REPL."}
