import os
import json
import re
import subprocess
import time
from dotenv import load_dotenv

# Try to use litellm if available, otherwise fallback to google.genai
try:
    from litellm import completion
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    try:
        from google import genai
        from google.genai import types
        GENAI_AVAILABLE = True
    except ImportError:
        GENAI_AVAILABLE = False
        print("Error: Neither litellm nor google-genai is installed.")
        print("Run: pip install litellm OR pip install google-genai")
        exit(1)

load_dotenv()

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WORKFLOW_FILE = os.path.join(ROOT_DIR, 'scripts', 'author-cn-stubs.workflow.js')
PROMPT_TEMPLATE_FILE = os.path.join(ROOT_DIR, 'scripts', 'prompt_template.txt')
SCAFFOLD_SCRIPT = os.path.join(ROOT_DIR, 'scripts', 'scaffold-lesson.sh')
MODEL_NAME = os.getenv('MODEL_NAME', 'gemini/gemini-2.5-pro') # default for litellm, or just gemini-2.5-pro for google-genai

def extract_worklist():
    with open(WORKFLOW_FILE, 'r') as f:
        content = f.read()
    
    # Extract the JSON array from `const WORKLIST = [...]`
    match = re.search(r'const WORKLIST\s*=\s*(\[.*?\]);?', content, re.DOTALL)
    if not match:
        raise ValueError("Could not find WORKLIST in workflow file")
    
    worklist_json = match.group(1)
    
    # The JSON string might not be strictly valid JSON if it has trailing commas or single quotes.
    # Fortunately the given file has valid JSON format for the array.
    try:
        return json.loads(worklist_json)
    except json.JSONDecodeError as e:
        print(f"Error parsing WORKLIST json: {e}")
        # Very hacky fallback if strict json fails
        import ast
        return ast.literal_eval(worklist_json)

def call_llm(prompt):
    print(f"Calling LLM with model: {MODEL_NAME}...")
    if LITELLM_AVAILABLE:
        response = completion(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content
    else:
        # Fallback to google-genai
        client = genai.Client()
        # strip the litellm prefix if present
        model = MODEL_NAME.replace('gemini/', '')
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        return response.text

def parse_and_save_blocks(text, base_dir, svg_name):
    """
    Parses markdown code blocks with file names like ```docs/en.md and saves them.
    """
    blocks = re.findall(r'```(.*?)\n(.*?)```', text, re.DOTALL)
    
    saved_files = []
    for header, content in blocks:
        header = header.strip()
        if 'docs/en.md' in header:
            path = os.path.join(base_dir, 'docs', 'en.md')
        elif 'code/main.py' in header:
            path = os.path.join(base_dir, 'code', 'main.py')
        elif 'quiz.json' in header:
            path = os.path.join(base_dir, 'quiz.json')
        elif svg_name in header or header.endswith('.svg') or 'mermaid' in header:
            path = os.path.join(base_dir, 'assets', svg_name)
        else:
            continue
            
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(content.strip() + "\n")
        saved_files.append(path)
        
    return saved_files

def main():
    worklist = extract_worklist()
    print(f"Found {len(worklist)} lessons to author.")
    
    with open(PROMPT_TEMPLATE_FILE, 'r') as f:
        prompt_template = f.read()

    # Process sequentially to respect rate limits
    for i, lesson in enumerate(worklist):
        print(f"\n[{i+1}/{len(worklist)}] Processing: {lesson['title']}")
        
        lesson_dir = os.path.join(ROOT_DIR, lesson['dir'])
        docs_file = os.path.join(lesson_dir, 'docs', 'en.md')
        
        # Check if already generated
        if os.path.exists(docs_file):
            with open(docs_file, 'r') as f:
                content = f.read()
                # If it's more than just the template skeleton, skip it
                if len(content.splitlines()) > 50:
                    print(f"Skipping {lesson['title']} - already generated.")
                    continue
        
        # 1. Scaffold directory
        # lesson['dir'] is like "phases/04-error-control-and-link-protocols/27-crc-polynomial-math"
        parts = lesson['dir'].split('/')
        phase_dir = parts[1]
        lesson_slug = parts[2]
        
        cmd = [SCAFFOLD_SCRIPT, phase_dir, lesson_slug, lesson['title']]
        print(f"Running scaffold: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=ROOT_DIR, check=False) # check=False because it might fail if dir exists
        
        # 2. Prepare Prompt
        prompt = prompt_template.format(
            title=lesson['title'],
            phase=lesson['phase'],
            chapter=lesson['chapter'] or "N/A",
            section=lesson['section'] or "N/A",
            svgName=lesson.get('svgName', 'concept.svg')
        )
        
        # 3. Call LLM
        try:
            response_text = call_llm(prompt)
        except Exception as e:
            print(f"Error calling LLM: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
            try:
                response_text = call_llm(prompt)
            except Exception as e2:
                print(f"Failed again: {e2}. Skipping.")
                continue
                
        # 4. Parse and Save
        saved = parse_and_save_blocks(response_text, lesson_dir, lesson.get('svgName', 'concept.svg'))
        print(f"Saved {len(saved)} files for {lesson['title']}")
        
        # Rate limiting sleep
        print("Waiting 5 seconds before next lesson...")
        time.sleep(5)

if __name__ == "__main__":
    main()
