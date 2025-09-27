import os
import sys
import re
import base64
import requests
from io import BytesIO
try:
    from PIL import Image
except Exception:
    Image = None


def _save_and_open_image_from_result(result, out_path="output.jpg"):
    """Try to find an image in the result (url, data url, b64, bytes, or PIL Image), save it to out_path, and open it on Windows.
    Returns out_path if saved, else None.
    """
    def find_image(obj):
        if obj is None:
            return None
        # bytes
        if isinstance(obj, (bytes, bytearray)):
            return ("bytes", bytes(obj))
        # Pillow image
        try:
            if Image is not None and isinstance(obj, Image.Image):
                return ("pil", obj)
        except Exception:
            pass
        # string -> url or data url or raw base64
        if isinstance(obj, str):
            if obj.startswith("http://") or obj.startswith("https://"):
                return ("url", obj)
            if obj.startswith("data:image/"):
                return ("dataurl", obj)
            # Heuristic: long base64 string
            if len(obj) > 200 and re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", obj[:1000]):
                return ("b64", obj)
        # dict/list -> search recursively
        if isinstance(obj, dict):
            for v in obj.values():
                found = find_image(v)
                if found:
                    return found
        if isinstance(obj, (list, tuple, set)):
            for v in obj:
                found = find_image(v)
                if found:
                    return found
        return None

    found = find_image(result)
    if not found:
        print("No image-like field found in result.")
        return None

    typ, data = found
    try:
        if typ == "url":
            r = requests.get(data, timeout=30)
            r.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(r.content)
        elif typ == "dataurl":
            m = re.match(r"data:image/\w+;base64,(.+)", data)
            b = base64.b64decode(m.group(1)) if m else base64.b64decode(data)
            with open(out_path, "wb") as f:
                f.write(b)
        elif typ == "b64":
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(data))
        elif typ == "bytes":
            with open(out_path, "wb") as f:
                f.write(data)
        elif typ == "pil":
            data.save(out_path)
        else:
            print("Unhandled image type:", typ)
            return None
    except Exception as e:
        print("Failed saving image:", e)
        return None

    # Try to open on Windows
    try:
        if os.name == 'nt':
            os.startfile(out_path)
        else:
            # Fallback: print path for manual opening
            print("Saved output image to:", out_path)
    except Exception as e:
        print("Saved to", out_path, "but couldn't open automatically:", e)
    return out_path


def main():
    # Accept image path from env or first arg; default is placeholder
    image_path = os.environ.get("IMAGE_PATH") or (sys.argv[1] if len(sys.argv) > 1 else "cavity.jpg")

    # Read API key from environment for safety; fallback to the hardcoded key if present
    api_key = os.environ.get("ROBOFLOW_API_KEY") or #"*************""

    # Basic validation to avoid running heavy imports and network calls when inputs are missing
    if image_path == "YOUR_IMAGE.jpg" or not os.path.isfile(image_path):
        print("Image not provided or not found. Set IMAGE_PATH env var or pass an image path as the first argument.")
        print(f"Tried: {image_path}")
        return

    if not api_key:
        print("API key not found. Set ROBOFLOW_API_KEY in your environment.")
        return

    # Import the heavy SDK only after validation
    try:
        from inference_sdk import InferenceHTTPClient
    except Exception as e:
        print("Failed to import inference_sdk:", e)
        return

    client = InferenceHTTPClient(
        api_url="https://serverless.roboflow.com",
        api_key=api_key
    )

    try:
        result = client.run_workflow(
            workspace_name="dentalissuedetectorhackgt12",
            workflow_id="small-object-detection-sahi",
            images={
                "image": image_path
            },
            use_cache=True  # cache workflow definition for 15 minutes
        )

        # Print a short summary of the result to avoid dumping large or sensitive data
        print("Workflow run completed. Result type:", type(result))
        if hasattr(result, 'keys'):
            print("Result keys:", list(result.keys()))
        else:
            print(result)

        # Attempt to save and open the first image found in the result (if any).
        try:
            saved = _save_and_open_image_from_result(result)
            if saved:
                print("Saved output image to:", saved)
        except Exception as e:
            print("Failed to save/open output image:", e)
    except Exception as e:
        # Redact API key if it appears in error messages
        err = str(e).replace(api_key, "<REDACTED_API_KEY>")
        print("Workflow invocation failed:", err)


if __name__ == "__main__":
    main()
