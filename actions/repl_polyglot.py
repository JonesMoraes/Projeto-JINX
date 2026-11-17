"""Bounded persistent Python and Node.js REPL worker sessions."""
from __future__ import annotations

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

_PY_WORKER = r'''import ast, contextlib, io, json, sys, traceback
namespace = {"__name__": "__jinx_repl__"}
for line in sys.stdin:
 try:
  req = json.loads(line); output = io.StringIO(); code = req.get("code", "")
  with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
   tree = ast.parse(code, "<jinx-repl>", "exec")
   if tree.body and isinstance(tree.body[-1], ast.Expr):
    final = ast.Expression(tree.body.pop().value)
    if tree.body: exec(compile(tree, "<jinx-repl>", "exec"), namespace)
    value = eval(compile(final, "<jinx-repl>", "eval"), namespace)
    if value is not None: print(repr(value))
   else: exec(compile(tree, "<jinx-repl>", "exec"), namespace)
  response = {"ok": True, "output": output.getvalue()}
 except BaseException:
  response = {"ok": False, "output": output.getvalue() if "output" in locals() else "", "error": traceback.format_exc()}
 sys.__stdout__.write(json.dumps(response, ensure_ascii=False) + "\n"); sys.__stdout__.flush()
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
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                       errors="replace", bufsize=1, creationflags=flags)
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
