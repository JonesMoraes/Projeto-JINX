"""
JINX action - Check default microphone and speaker devices.

This action provides information about the current audio input/output devices
being used by JINX, including the system default devices.

Usage:
    - Command: "verificar microfone" or "check microphone"
    - Voice: "JINX, verificar microfone"
"""

from core import outcome


def check_default_microphone() -> str:
    """Check and return information about the default microphone."""
    try:
        import sounddevice as sd
        
        # Get default input device
        default_input_idx = sd.default.device[0]
        
        if default_input_idx < 0:
            return "No default microphone detected. Please connect a microphone."
        
        devices = sd.query_devices()
        default_input = devices[default_input_idx]
        
        info = [
            f"Default Microphone (System):",
            f"  Index: {default_input_idx}",
            f"  Name: {default_input.get('name', 'Unknown')}",
            f"  Max Input Channels: {default_input.get('max_input_channels', 0)}",
            f"  Sample Rate: {default_input.get('default_samplerate', 'Unknown')}",
            f"  Host API: {default_input.get('hostapi', -1)}",
        ]
        
        # Check if this is a pseudo-device
        from core.audio_devices import _is_pseudo
        if _is_pseudo(default_input.get('name', '')):
            info.append("  Note: This is a pseudo-device (alias). JINX will use the actual hardware.")
        
        return "\n".join(info)
        
    except ImportError:
        return "sounddevice not installed. Install with: pip install sounddevice"
    except Exception as e:
        return f"Error checking microphone: {e}"


def check_default_speaker() -> str:
    """Check and return information about the default speaker."""
    try:
        import sounddevice as sd
        
        # Get default output device
        default_output_idx = sd.default.device[1]
        
        if default_output_idx < 0:
            return "No default speaker detected."
        
        devices = sd.query_devices()
        default_output = devices[default_output_idx]
        
        info = [
            f"Default Speaker (System):",
            f"  Index: {default_output_idx}",
            f"  Name: {default_output.get('name', 'Unknown')}",
            f"  Max Output Channels: {default_output.get('max_output_channels', 0)}",
            f"  Sample Rate: {default_output.get('default_samplerate', 'Unknown')}",
            f"  Host API: {default_output.get('hostapi', -1)}",
        ]
        
        # Check if this is a pseudo-device
        from core.audio_devices import _is_pseudo
        if _is_pseudo(default_output.get('name', '')):
            info.append("  Note: This is a pseudo-device (alias). JINX will use the actual hardware.")
        
        return "\n".join(info)
        
    except ImportError:
        return "sounddevice not installed. Install with: pip install sounddevice"
    except Exception as e:
        return f"Error checking speaker: {e}"


def check_current_jinx_devices() -> str:
    """Check which devices JINX is currently configured to use."""
    from memory.config_manager import get_input_device, get_output_device
    
    input_device = get_input_device()
    output_device = get_output_device()
    
    info = [
        "Current JINX Configuration:",
        f"  Input Device: {input_device if input_device else '(System Default)'}",
        f"  Output Device: {output_device if output_device else '(System Default)'}",
    ]
    
    return "\n".join(info)


def check_all_audio_devices() -> str:
    """List all available audio devices."""
    try:
        import sounddevice as sd
        
        devices = sd.query_devices()
        
        if not devices:
            return "No audio devices found."
        
        info = ["Available Audio Devices:"]
        info.append("=" * 60)
        
        for idx, dev in enumerate(devices):
            name = dev.get('name', 'Unknown')
            max_in = dev.get('max_input_channels', 0)
            max_out = dev.get('max_output_channels', 0)
            samplerate = dev.get('default_samplerate', 'Unknown')
            
            # Mark default devices
            markers = []
            if idx == sd.default.device[0]:
                markers.append("[DEFAULT INPUT]")
            if idx == sd.default.device[1]:
                markers.append("[DEFAULT OUTPUT]")
            
            marker_str = " ".join(markers) if markers else ""
            
            info.append(f"  {idx}: {name} {marker_str}")
            info.append(f"      Input Channels: {max_in}, Output Channels: {max_out}")
            info.append(f"      Sample Rate: {samplerate}")
        
        return "\n".join(info)
        
    except ImportError:
        return "sounddevice not installed. Install with: pip install sounddevice"
    except Exception as e:
        return f"Error listing devices: {e}"


def check_audio_devices() -> str:
    """Main function to check all audio devices."""
    sections = [
        "=" * 60,
        "AUDIO DEVICE CHECK",
        "=" * 60,
        "",
        check_current_jinx_devices(),
        "",
        check_default_microphone(),
        "",
        check_default_speaker(),
        "",
        check_all_audio_devices(),
        "",
        "=" * 60,
        "Note: JINX will use system default devices when not configured.",
        "To use a specific device, configure it in settings.",
        "=" * 60,
    ]
    
    return "\n".join(sections)


# JINX action registration
async def action_check_microphone(session):
    """Check microphone and audio devices."""
    result = check_audio_devices()
    return outcome.answered("check_microphone", result)


# Tool declaration for auto-discovery by action_loader
TOOL = {
    "name": "check_microphone",
    "description": "Check and display information about audio devices: current JINX configuration, system default microphone and speaker, and all available audio devices. Useful for troubleshooting microphone issues.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    },
    "handler": action_check_microphone,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}
