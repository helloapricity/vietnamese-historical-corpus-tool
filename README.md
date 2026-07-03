# Vietnamese Historical Monolingual Corpus Annotation Tool

A full-stack web application designed to facilitate the creation of a monolingual corpus for Vietnamese historical texts (Chữ Quốc Ngữ). This tool provides an integrated pipeline for digitizing PDF documents, correcting OCR errors, splitting sentences, and assigning Named Entity Recognition (NER) tags.

## 🚀 Technical Solution

This project leverages modern web frameworks and local Large Language Models (LLMs) to process historical texts securely and efficiently.

### Architecture
- **Frontend**: Next.js (React), Tailwind CSS
- **Backend**: FastAPI (Python)
- **Local AI Engine**: Ollama (Running locally to ensure data privacy)

### Core Technologies
1. **OCR Extraction**: 
   - Uses `PyMuPDF` (`fitz`) to extract raw text blocks and their bounding boxes directly from digital PDFs.
2. **OCR Error Correction**: 
   - Uses **Qwen 2.5 (7B)** via Ollama to intelligently fix spelling errors and recognize historical context.
3. **Sentence Splitting**: 
   - Uses `underthesea` (a specialized Vietnamese NLP toolkit) to accurately tokenize paragraphs into sentences.
4. **Named Entity Recognition (NER)**:
   - **LLM-Based**: Uses **Qwen 2.5 (7B)** via Ollama to automatically extract historical entities.
   - **Dictionary-Based**: Uses a custom `dictionary.json` to map exact phrases to entity labels.

---

## 🛠 Setup & Installation

### Prerequisites
1. **Node.js** (v18+)
2. **Python** (v3.10+)
3. **Ollama**: Installed and running locally.
   - You must pull the Qwen 2.5 model before starting:
     ```bash
     ollama run qwen2.5:7b
     ```

### 1. Backend Setup
1. Open a terminal and navigate to the `backend` directory.
2. Install the required Python dependencies:
   ```bash
   pip install fastapi uvicorn pydantic requests pymupdf underthesea pdf2image
   ```
3. Run the backend server:
   ```bash
   # You can use the provided batch script if available
   start.bat
   # OR run manually
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### 2. Frontend Setup
1. Open a new terminal and navigate to the `frontend` directory.
2. Install the Node dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
4. Access the UI at `http://localhost:3000`.

---

## 📂 Document Management (PDFs)

### Where to place source PDFs?
All raw PDF documents must be placed inside the `raw_file/` folder located at the root of the project (at the same level as `backend/` and `frontend/`). 
- If the folder does not exist, create it: `raw_file/`.
- The system will automatically scan this folder and display the available PDFs in the dropdown menu on the UI.

### Document Acronyms / IDs
When processing a file (e.g., `Quoc Su Di Bien.pdf`), the system automatically assigns an **acronym** based on the filename (or a predefined mapping in the backend logic) to generate the final IDs (e.g., `HVQ_025`). 
- **To adjust the acronym mapping**, edit the `get_acronym()` function inside `backend/main.py` or modify the `mapping.json` file if one is configured in the backend folder.

---

## 📖 How to Use the Tool

### Step 1: Select and Process a Document
1. Select a PDF from the dropdown menu at the top of the UI.
2. Use the **Trang trước / Trang sau** buttons to navigate through the PDF pages.

### Step 2: OCR Extraction & Correction (Tab 1)
1. Navigate to the **1. Sửa lỗi** tab.
2. Click **Chạy OCR** to extract text blocks from the current page.
3. You can click on any bounding box on the image to locate its corresponding text.
4. **Merge Blocks**: If multiple blocks belong to the same paragraph, select their checkboxes and click **Gộp block**. They will be merged seamlessly.
5. **AI Correction**: Select blocks with OCR errors and click **Gọi Qwen Sửa Lỗi**. The AI will suggest a corrected version, which you can choose to Accept or Deny.
6. Click **Đánh dấu xong** to lock the block.

### Step 3: Sentence Splitting (Tab 2)
1. Navigate to the **2. Tách câu** tab.
2. Ensure you have input the correct **Mã Chương** (Chapter ID) in the input box (e.g., `001`). This ensures the sentence IDs are generated sequentially (`HVQ_025_001_000001`).
3. Click **Tự động Tách (Underthesea)**. The system will convert all extracted text on the current page into individual sentences.
4. Review the sentences and manually adjust the boundaries or IDs if necessary.

### Step 4: Named Entity Recognition (Tab 3)
1. Navigate to the **3. Gán nhãn** tab.
2. **Automated NER (LLM)**: Click **Tự Động Gán (Qwen)** to let the AI analyze the sentences and extract entities (PER, LOC, ORG, TME, etc.).
3. **Dictionary-based NER**: Click **Tự Động Gán (Từ điển)** to perform a strict match using the built-in dictionary.
   - To update the dictionary, click **Nạp Dictionary**, paste your JSON array of entities, and apply it.
4. **Manual Tagging**: Highlight any word in a sentence with your mouse, then click one of the colored tag buttons (PER, LOC, ORG...) to manually assign an entity.

### Step 5: Save Your Work
1. Click the **Lưu File** button on the right side of the toolbar.
2. The system will save all your progress (across all pages) into the `output_data/` folder as `.txt`, `.tsv`, and `.json` files, preserving the complete workspace state so you can resume later.
