import gradio as gr

def process_text(text, operation):
    if operation == "uppercase":
        return text.upper()
    elif operation == "lowercase":
        return text.lower()
    elif operation == "reverse":
        return text[::-1]
    return text

interface = gr.Interface(
    fn=process_text,
    inputs=[
        gr.Textbox(label="入力テキスト"),
        gr.Dropdown(["uppercase", "lowercase", "reverse"], label="操作")
    ],
    outputs=gr.Textbox(label="結果"),
    title="テキスト処理アプリ"
)

interface.launch(server_name="0.0.0.0", server_port=7860)