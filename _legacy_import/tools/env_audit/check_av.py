import av
import inspect
sig = inspect.signature(av.open)
print("av.open parameters:", list(sig.parameters.keys()))
print("av version:", av.__version__)

# Check if metadata_errors is supported
if "metadata_errors" in sig.parameters:
    print("metadata_errors: SUPPORTED")
else:
    print("metadata_errors: NOT SUPPORTED")
    print("faster-whisper 1.2.1 requires this. Need av >= 14.2.0 or a monkey-patch.")
