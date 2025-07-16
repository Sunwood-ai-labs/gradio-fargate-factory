import gradio as gr
from PIL import Image, ImageFilter

def apply_filter(image, filter_type):
    if filter_type == "blur":
        return image.filter(ImageFilter.BLUR)
    elif filter_type == "sharpen":
        return image.filter(ImageFilter.SHARPEN)
    elif filter_type == "edge":
        return image.filter(ImageFilter.FIND_EDGES)
    return image

interface = gr.Interface(
    fn=apply_filter,
    inputs=[
        gr.Image(type="pil"),
        gr.Dropdown(["blur", "sharpen", "edge"], label="フィルター")
    ],
    outputs=gr.Image(type="pil"),
    title="画像フィルターアプリ"
)

interface.launch(server_name="0.0.0.0", server_port=7860)