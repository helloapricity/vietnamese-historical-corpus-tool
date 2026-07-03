from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import shutil
import json
import re
import base64
import yaml
import fitz  # PyMuPDF
import requests
from typing import List, Dict, Any
from pdf2image import convert_from_path
from pathlib import Path

app = FastAPI(title="Annotation Backend")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "raw_file"
IMAGES_DIR = BASE_DIR / "backend_data" / "images"
OUTPUT_DIR = BASE_DIR / "output_data"

# Create directories if they don't exist
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class SaveDataRequest(BaseModel):
    acronym: str
    page_id: str
    raw_ocr: str
    ocr_blocks: List[Dict] = []
    sentences: List[Dict[str, Any]]
    ner_data: List[Dict[str, Any]]
    skipped_pages: List[int] = []

@app.get("/")
def read_root():
    return {"message": "Annotation Backend is running"}

@app.post("/api/upload-pdf")
async def process_pdf(filename: str):
    pdf_path = RAW_DIR / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found in raw_file directory")
    
    # Define document folder based on acronym convention (mocking acronym logic for now, using filename stem)
    doc_id = pdf_path.stem
    doc_images_dir = IMAGES_DIR / doc_id
    doc_images_dir.mkdir(exist_ok=True)
    
    try:
        # Note: pdf2image requires poppler installed on the system
        images = convert_from_path(str(pdf_path))
        saved_images = []
        for i, image in enumerate(images):
            page_name = f"page_{i+1:03d}.jpg"
            image_path = doc_images_dir / page_name
            image.save(str(image_path), "JPEG")
            saved_images.append(page_name)
        return {"status": "success", "doc_id": doc_id, "pages": saved_images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import requests
import json
import unicodedata

def get_acronym(filename: str) -> str:
    try:
        norm_filename = unicodedata.normalize('NFC', filename).strip()
        with open("mapping.json", "r", encoding="utf-8") as f:
            mapping = json.load(f)
            
            # Normalize dictionary keys
            norm_mapping = {unicodedata.normalize('NFC', k).strip(): v for k, v in mapping.items()}
            
            if norm_filename in norm_mapping:
                return norm_mapping[norm_filename]
                
            # Fallback: check without extension
            name_without_ext = norm_filename.rsplit('.', 1)[0]
            for k, v in norm_mapping.items():
                if k.rsplit('.', 1)[0] == name_without_ext:
                    return v
    except Exception as e:
        print("Lỗi mapping:", e)
        pass
    return filename.rsplit('.', 1)[0] if '.' in filename else filename

@app.post("/api/save")
async def save_annotation(data: SaveDataRequest):
    try:
        acronym = get_acronym(data.acronym)
        
        # Tên file không chứa page_id nữa vì giờ ta đã lưu cộng dồn (accumulated) nhiều trang
        raw_txt_path = OUTPUT_DIR / f"{acronym}_raw.txt"
        with open(raw_txt_path, "w", encoding="utf-8") as f:
            f.write(data.raw_ocr)
        
        seg_tsv_path = OUTPUT_DIR / f"{acronym}_seg.tsv"
        with open(seg_tsv_path, "w", encoding="utf-8") as f:
            for s in data.sentences:
                s_id = s.get('sentence_id') or s.get('id', '')
                s_text = s.get('sentence') or s.get('text', '')
                f.write(f"{s_id}\t{s_text}\n")
        
        ner_json_path = OUTPUT_DIR / f"{acronym}_ner.json"
        with open(ner_json_path, "w", encoding="utf-8") as f:
            json.dump(data.ner_data, f, ensure_ascii=False, indent=2)
            
        # Lưu toàn bộ trạng thái Workspace (Để phục hồi sau)
        workspace_path = OUTPUT_DIR / f"{acronym}_workspace.json"
        with open(workspace_path, "w", encoding="utf-8") as f:
            json.dump(data.model_dump(), f, ensure_ascii=False, indent=2)
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LoadWorkspaceRequest(BaseModel):
    acronym: str

@app.post("/api/load-workspace")
async def load_workspace(data: LoadWorkspaceRequest):
    try:
        acronym = get_acronym(data.acronym)
        workspace_path = OUTPUT_DIR / f"{acronym}_workspace.json"
        if workspace_path.exists():
            with open(workspace_path, "r", encoding="utf-8") as f:
                return {"status": "success", "data": json.load(f)}
        return {"status": "not_found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import requests

# Mock endpoints for AI Models
class OCRRequest(BaseModel):
    text: str

@app.post("/api/process-ocr")
async def process_ocr_correction(data: OCRRequest):
    try:
        # Prompt for Qwen 2.5 to correct spelling
        prompt = f"""Bạn là một chuyên gia lịch sử Việt Nam. Nhiệm vụ của bạn là sửa lỗi chính tả chữ Quốc ngữ bị nhận diện sai bởi OCR từ văn bản sau. Chỉ trả về kết quả đã sửa, không giải thích.
        
Văn bản gốc:
{data.text}
"""
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5:7b",
                "prompt": prompt,
                "stream": False
            }
        )
        if response.status_code == 200:
            result = response.json().get("response", "")
            return {"corrected_text": result}
        else:
            raise HTTPException(status_code=500, detail="Ollama API error")
    except Exception as e:
        return {"corrected_text": data.text, "error": str(e)}

class SentencesRequest(BaseModel):
    text: str
    doc_id: str
    chapter_id: str = "001"
    start_index: int = 0

@app.post("/api/process-sentences")
async def process_sentences(data: SentencesRequest):
    try:
        from underthesea import sent_tokenize
        sentences = sent_tokenize(data.text)
        
        acronym = get_acronym(data.doc_id)
        
        result = []
        for i, s in enumerate(sentences):
            # Format: [matacpham]_[chapter_id]_[sentence_id]
            s_id = f"{acronym}_{data.chapter_id}_{data.start_index + i + 1:06d}"
            result.append({"id": s_id, "text": s})
            
        return {"sentences": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NERRequest(BaseModel):
    sentences: List[Dict[str, Any]]

@app.post("/api/process-ner-dict")
async def process_ner_dict(data: NERRequest):
    try:
        dictionary_items = []
        try:
            import json
            with open("dictionary.json", "r", encoding="utf-8") as f:
                dictionary_items = json.load(f)
        except Exception as e:
            print("Chưa có dictionary.json hoặc file trống:", e)

        results = []
        for s in data.sentences:
            s_id = s["id"]
            s_text = s["text"]
            formatted_entities = []
            
            for dict_ent in dictionary_items:
                dict_text = dict_ent.get("text", "")
                dict_label = dict_ent.get("label", "").upper()
                if not dict_text:
                    continue
                    
                if dict_text.lower() in s_text.lower():
                    # Check if already added
                    if not any(e["text"].lower() == dict_text.lower() for e in formatted_entities):
                        formatted_entities.append({
                            "text": dict_text,
                            "label": dict_label
                        })
                    
            results.append({
                "sentence_id": s_id,
                "sentence": s_text,
                "entities": formatted_entities,
                "isCompleted": False
            })
            
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


import json
import re

@app.post("/api/process-ner")
async def process_ner(data: NERRequest):
    try:
        # Load dictionary for Pass 2
        dictionary_items = []
        try:
            with open("dictionary.json", "r", encoding="utf-8") as f:
                dictionary_items = json.load(f)
        except Exception as e:
            print("Chưa có dictionary.json hoặc file trống:", e)

        results = []
        for s in data.sentences:
            s_id = s["id"]
            s_text = s["text"]
            # Load prompt from YAML
            try:
                with open("prompts.yaml", "r", encoding="utf-8") as f:
                    prompts = yaml.safe_load(f)
                    prompt_template = prompts.get("ner_prompt", "")
            except Exception as e:
                print("Lỗi đọc file prompts.yaml:", e)
                raise HTTPException(status_code=500, detail="Không tìm thấy file prompts.yaml")

            prompt = prompt_template.format(s_text=s_text)

            print(f"\n--- GỬI YÊU CẦU LÊN QWEN ---")
            print(f"Câu: {s_text}")

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                }
            )
            
            formatted_entities = []
            if response.status_code == 200:
                raw_result = response.json().get("response", "{}")
                print(f"--- KẾT QUẢ TỪ QWEN TRẢ VỀ ---")
                print(f"Raw JSON: {raw_result}\n")
                
                try:
                    clean_json = re.sub(r'```json|```', '', raw_result).strip()
                    entities_data = json.loads(clean_json)
                    
                    # Handle case where Qwen returns {"entities": [...]}
                    if isinstance(entities_data, dict) and "entities" in entities_data:
                        items = entities_data["entities"]
                    # Handle case where Qwen ignores root object and just returns [...]
                    elif isinstance(entities_data, list):
                        items = entities_data
                    # Handle case where Qwen just returns a single object {"text": "...", "label": "..."}
                    elif isinstance(entities_data, dict) and "text" in entities_data and "label" in entities_data:
                        items = [entities_data]
                    else:
                        items = []
                        
                    for ent in items:
                        if "text" in ent and "label" in ent:
                            formatted_entities.append({
                                "text": str(ent["text"]),
                                "label": str(ent["label"]).upper()
                            })
                            
                    # --- PASS 2: DICTIONARY OVERRIDE & FALLBACK ---
                    for dict_ent in dictionary_items:
                        dict_text = dict_ent.get("text", "")
                        dict_label = dict_ent.get("label", "").upper()
                        if not dict_text:
                            continue
                            
                        # Chỉ áp dụng nếu từ điển xuất hiện trong câu gốc
                        if dict_text.lower() in s_text.lower():
                            found_in_qwen = False
                            for ent in formatted_entities:
                                # Nếu Qwen đã bắt được từ này
                                if ent["text"].lower() == dict_text.lower():
                                    found_in_qwen = True
                                    if ent["label"] != dict_label:
                                        print(f"-> [Pass 2 - Dictionary] Sửa nhãn Qwen: {ent['text']} ({ent['label']} -> {dict_label})")
                                        ent["label"] = dict_label
                                    break
                                    
                            # Nếu Qwen bỏ sót hoàn toàn
                            if not found_in_qwen:
                                formatted_entities.append({
                                    "text": dict_text,
                                    "label": dict_label
                                })
                                print(f"-> [Pass 2 - Dictionary] Tự động bổ sung: {dict_text} [{dict_label}]")
                                
                    print(f"-> Final Parsed Entities: {formatted_entities}")
                except Exception as e:
                    print("-> JSON Parse Error:", e, raw_result)
            
            results.append({
                "sentence_id": s_id,
                "sentence": s_text,
                "entities": formatted_entities
            })
            
        return {"data": results}
    except Exception as e:
        print("Lỗi hệ thống NER:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

class SaveRequest(BaseModel):
    doc_id: str
    page_id: str
    raw_ocr: str
    sentences: List[Dict[str, str]]
    ner_data: List[Dict]

@app.get("/api/documents")
async def get_documents():
    try:
        raw_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_file")
        files = [f for f in os.listdir(raw_dir) if f.lower().endswith('.pdf')]
        return {"documents": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DictionaryUpdate(BaseModel):
    new_items: List[Dict[str, str]]

@app.post("/api/update-dictionary")
async def update_dictionary(data: DictionaryUpdate):
    try:
        dict_path = os.path.join(os.path.dirname(__file__), "dictionary.json")
        existing_items = []
        if os.path.exists(dict_path):
            with open(dict_path, "r", encoding="utf-8") as f:
                try:
                    existing_items = json.load(f)
                except:
                    existing_items = []
        
        # Gộp data cũ và mới
        all_items = existing_items + data.new_items
        
        # Xóa trùng lặp (Duplicate) dựa trên cặp (text, label)
        unique_items = []
        seen = set()
        for item in all_items:
            text = str(item.get("text", "")).strip()
            label = str(item.get("label", "")).strip().upper()
            if text and label:
                identifier = (text, label)
                if identifier not in seen:
                    seen.add(identifier)
                    unique_items.append({"text": text, "label": label})
                    
        # Lưu lại file
        with open(dict_path, "w", encoding="utf-8") as f:
            json.dump(unique_items, f, ensure_ascii=False, indent=2)
            
        return {"status": "success", "total_items": len(unique_items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-data")
async def save_data(data: SaveRequest):
    try:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_file", "output")
        os.makedirs(output_dir, exist_ok=True)
        
        base_name = f"{data.doc_id}_{data.page_id}"
        
        # 1. Lưu _raw.txt
        with open(os.path.join(output_dir, f"{base_name}_raw.txt"), "w", encoding="utf-8") as f:
            f.write(data.raw_ocr)
            
        # 2. Lưu _seg.tsv
        with open(os.path.join(output_dir, f"{base_name}_seg.tsv"), "w", encoding="utf-8") as f:
            for s in data.sentences:
                f.write(f"{s['id']}\t{s['text']}\n")
                
        # 3. Lưu _ner.json
        with open(os.path.join(output_dir, f"{base_name}_ner.json"), "w", encoding="utf-8") as f:
            json.dump(data.ner_data, f, ensure_ascii=False, indent=2)
            
        return {"status": "success", "message": "Saved 3 files successfully to output folder."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LoadPdfRequest(BaseModel):
    file_name: str
    page_index: int = 0

import datetime
import unicodedata

@app.post("/api/run-ocr")
async def run_ocr(data: LoadPdfRequest):
    try:
        pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_file", data.file_name)
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="Không tìm thấy file PDF.")
            
        doc = fitz.open(pdf_path)
        if data.page_index >= len(doc):
             raise HTTPException(status_code=400, detail="Page index vượt quá số trang PDF.")
             
        page = doc.load_page(data.page_index)
        page_w = page.rect.width
        page_h = page.rect.height
        
        # Lấy toàn bộ blocks thay vì text đơn thuần
        raw_blocks = page.get_text("blocks")
        blocks_data = []
        full_text_length = 0
        
        for idx, b in enumerate(raw_blocks):
            # b = (x0, y0, x1, y1, "text", block_no, block_type)
            if b[6] == 0:  # Text block
                text_content = b[4].strip()
                if not text_content: continue
                # Chuyển các dòng thành 1 đoạn văn duy nhất (xóa \n)
                text_content = " ".join(text_content.split())
                # Chuẩn hóa NFC
                text_content = unicodedata.normalize("NFC", text_content)
                full_text_length += len(text_content)
                
                # Tính % tọa độ
                blocks_data.append({
                    "id": f"block_p{data.page_index}_{idx}",
                    "text": text_content,
                    "box": {
                        "left": (b[0] / page_w) * 100,
                        "top": (b[1] / page_h) * 100,
                        "width": ((b[2] - b[0]) / page_w) * 100,
                        "height": ((b[3] - b[1]) / page_h) * 100
                    }
                })
        
        if not blocks_data:
            blocks_data.append({
                "id": f"empty_p{data.page_index}",
                "text": "(Không tìm thấy lớp Text trong trang PDF này. Vui lòng đảm bảo file là PDF đã được OCR sẵn hoặc bạn cần gõ tay).",
                "box": {"left": 0, "top": 0, "width": 100, "height": 100}
            })

        # --- TẠO LOG AUDIT ---
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_file", "output")
        os.makedirs(output_dir, exist_ok=True)
        log_path = os.path.join(output_dir, "ocr_audit.log")
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] OCR AUDIT (BLOCKS) - File: {data.file_name} - Trang: {data.page_index + 1}\n"
        log_entry += f"Số khối (Blocks) trích xuất: {len(blocks_data)} - Tổng ký tự: {full_text_length}.\n"
        log_entry += "-" * 50 + "\n"
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

        return {"status": "success", "blocks": blocks_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/load-pdf")
async def load_pdf(data: LoadPdfRequest):
    try:
        pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "raw_file", data.file_name)
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="Không tìm thấy file PDF.")
            
        # Dùng PyMuPDF để mở PDF
        doc = fitz.open(pdf_path)
        if data.page_index >= len(doc):
             raise HTTPException(status_code=400, detail="Page index vượt quá số trang PDF.")
             
        page = doc.load_page(data.page_index)
        # Tăng chất lượng ảnh (zoom x2)
        zoom_x = 2.0
        zoom_y = 2.0
        mat = fitz.Matrix(zoom_x, zoom_y)
        pix = page.get_pixmap(matrix=mat)
        
        # Chuyển đổi sang dạng base64
        img_bytes = pix.tobytes("jpeg")
        base64_encoded = base64.b64encode(img_bytes).decode("utf-8")
        
        return {
            "status": "success", 
            "total_pages": len(doc),
            "image_base64": f"data:image/jpeg;base64,{base64_encoded}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
