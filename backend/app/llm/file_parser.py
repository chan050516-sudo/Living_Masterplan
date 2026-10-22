import logging
import io

log = logging.getLogger(__name__)

def parse_uploaded_file(file_content: bytes, filename: str) -> str:
    """
    Parse uploaded file content into a string context block.
    Currently supports basic text extraction for txt, csv, md.
    """
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    try:
        if ext in ('txt', 'md', 'csv', 'json'):
            text = file_content.decode('utf-8')
            # Truncate to prevent token explosion (keep max 10k chars)
            if len(text) > 10000:
                text = text[:10000] + "\n...[TRUNCATED]"
            return f"\n[Attached Document: {filename}]\n{text}\n"
        
        # If PDF or others, return a placeholder (since parsing PDFs requires heavy dependencies)
        else:
            return f"\n[Attached Document: {filename}] (Binary file, content not parsed)\n"
            
    except Exception as e:
        log.warning(f"Failed to parse uploaded file {filename}: {e}")
        return f"\n[Attached Document: {filename}] (Error reading file)\n"