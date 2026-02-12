import re

def strip_sparql(text):
    text = re.sub(r"```(?:sparql)?", "", text, flags=re.IGNORECASE).strip()
    return text

def header_footer(text):
    if "PREFIX" not in text.upper():
        text = "PREFIX : <http://example.org/schema#>\n" + text

    if "LIMIT" not in text.upper():
        text += "\nLIMIT 10"
    
    return text

if __name__ == "__main__":
    text = "```sparql \n Heyyy from CODA !!"
    text = strip_sparql(text)
    text = header_footer(text)
    print(text)