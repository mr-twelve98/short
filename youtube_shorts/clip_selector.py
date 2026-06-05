import re
import logging

logger = logging.getLogger(__name__)

GEMINI_PROMPT_TEMPLATE = """
I am providing you with a transcript of a video. Please identify the most engaging moments (clips) that would make good YouTube Shorts.
For each clip, provide:
- A catchy Title
- A Hook (the first few seconds' content)
- Start time (in HH:MM:SS or MM:SS format)
- End time (in HH:MM:SS or MM:SS format)
- A brief explanation of why this clip was chosen

TRANSCRIPT:
{transcript}

Please output the clips in the following format:
Clip 1:
Title: [Title]
Hook: [Hook]
Start: [Start Time]
End: [End Time]
Why: [Reason]

...and so on.
"""

def generate_gemini_prompt(transcript_text):
    return GEMINI_PROMPT_TEMPLATE.format(transcript=transcript_text)

def parse_gemini_response(text):
    """
    Parses the Gemini response using flexible regex.
    Looks for Start, End, Title, etc.
    """
    clips = []

    # Split by "Clip X" or similar markers, or just try to find blocks of information
    # We'll look for blocks that contain at least Start and End

    # Use a more robust approach: find all occurrences of Start and End
    # and try to associate them with surrounding Title/Hook/Why

    # Let's split by "Clip X" markers or just look for each block individually
    # A more reliable way: find all "Start:" occurrences and treat everything until next "Start:" as a block

    # Pre-process: split by "Clip" marker if it exists, otherwise use double newline
    if re.search(r'Clip \d+', text, re.IGNORECASE):
        blocks = re.split(r'\n?(?=Clip \d+:?|CLIP \d+:?)', text, flags=re.IGNORECASE)
    else:
        blocks = re.split(r'\n\n+', text)

    for block in blocks:
        if not block.strip():
            continue
        start_match = re.search(r'Start:\s*([\d:]+)', block, re.IGNORECASE)
        end_match = re.search(r'End:\s*([\d:]+)', block, re.IGNORECASE)

        if start_match and end_match:
            start_str = start_match.group(1)
            end_str = end_match.group(1)

            title_match = re.search(r'Title:\s*(.*)', block, re.IGNORECASE)
            hook_match = re.search(r'Hook:\s*(.*)', block, re.IGNORECASE)
            why_match = re.search(r'Why:\s*(.*)', block, re.IGNORECASE)

            clips.append({
                'start': timestamp_to_seconds(start_str),
                'end': timestamp_to_seconds(end_str),
                'start_str': start_str,
                'end_str': end_str,
                'title': title_match.group(1).strip() if title_match else f"Clip {len(clips)+1}",
                'hook': hook_match.group(1).strip() if hook_match else "",
                'why': why_match.group(1).strip() if why_match else ""
            })

    return clips

def timestamp_to_seconds(ts):
    parts = ts.split(':')
    parts = [float(p) for p in parts]
    if len(parts) == 3: # HH:MM:SS
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2: # MM:SS
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1: # SS
        return parts[0]
    return 0
