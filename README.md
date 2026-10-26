# Sarvam Study Notes Reader

This project is hosted in the [`Simple-Notes-Analyzer`](https://github.com/shiveish/Simple-Notes-Analyzer) repository.

A small command-line reader that turns study documents into structured notes using the study method in [`prompts/study_notes.md`](prompts/study_notes.md).

It reads `.txt` and `.md` files directly. For PDFs and page images (`.pdf`, `.png`, `.jpg`, `.jpeg`), it uses Sarvam Document AI to digitise the material as Markdown, then uses Sarvam chat completion to create the notes.

## Setup

Requires Python 3.11+ and a Sarvam API key.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Add your key to `.env`:

```env
SARVAM_API_KEY=
```

The `.env` file is ignored by Git. You can also set `SARVAM_API_KEY` in your shell environment.

## Use

Start the web interface:

```sh
streamlit run app.py
```

Upload a document, choose its language if it is a PDF or image, then select **Create study notes**. Download the result as Markdown.

The command-line reader is also available:

```sh
python docs_reader.py path/to/lecture-notes.pdf
python docs_reader.py path/to/notes.md --output study-notes.md
python docs_reader.py path/to/hindi-notes.pdf --language hi-IN
```

By default, notes are written to the ignored `notes/` directory. The source document is sent to Sarvam when processing a PDF or image. Document AI Digitise supports PDFs up to 30 pages and 200 MB; larger PDFs need to be split first.

Long documents are processed in sections and then consolidated so the reader can cover the full source while staying within the chat model's context limits. This can make multiple chat requests.

## APIs used

- **Document AI Digitise** converts PDFs and page images into reading-order Markdown.
- **Chat Completion** applies the study-notes instructions using `sarvam-105b-conversations`.

See the [Document AI](https://docs.sarvam.ai/api/api-guides-tutorials/document-intelligence/overview) and [Chat Completion](https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview) guides for API details.

The web app uses [Streamlit](https://docs.streamlit.io/get-started/installation/command-line) and is suitable for local use or a Streamlit deployment.

## Publish and deploy

The source is available at [github.com/shiveish/Simple-Notes-Analyzer](https://github.com/shiveish/Simple-Notes-Analyzer). To deploy on Streamlit Community Cloud, choose that repository, branch `main`, and entrypoint `app.py`.

In the app's secrets settings, add `SARVAM_API_KEY = "your key"`; never commit `.env` or paste the key into GitHub. Streamlit will provide a separate `*.streamlit.app` URL for the running app.

The reader does not use field extraction; it produces explanatory notes rather than a fixed set of document fields.
