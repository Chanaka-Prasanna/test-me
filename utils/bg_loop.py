import asyncio
import threading

# Global event loop for background tasks
loop = asyncio.new_event_loop()
_loop_thread = None
_loop_lock = threading.Lock()


def _run_loop(loop_obj):
    asyncio.set_event_loop(loop_obj)
    print("[BG-LOOP] Event loop thread started")
    loop_obj.run_forever()


def is_background_loop_running():
    """Return True when the shared background loop is active."""
    global _loop_thread
    return _loop_thread is not None and _loop_thread.is_alive() and loop.is_running()


def start_background_loop():
    """Start the global asyncio event loop in a separate thread."""
    global _loop_thread

    with _loop_lock:
        if is_background_loop_running():
            return loop

        if loop.is_closed():
            raise RuntimeError("Background asyncio loop is closed and cannot be restarted.")

        _loop_thread = threading.Thread(
            target=_run_loop,
            args=(loop,),
            daemon=True,
            name="bot-bg-loop",
        )
        _loop_thread.start()
        return loop
