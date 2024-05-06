import argparse
import sys
import re
import json
from num2words import num2words

supported_languages = {
    'en': 'English',
    'de': 'German',
}

def year_to_words(year, language):
    # This function converts a year number into its spoken German form
    # You may need to expand this function to handle more cases
    if year < 2000:
        return f"{year // 100}hundert {year % 100}"
    else:
        return f"zweitausend {year % 1000}"
    
def prepare_text(text, language):
    if language == 'de':
        # Find all four-digit numbers in the text
        years = re.findall(r'\b\d{4}\b', text)
        for year in years:
            # Parse the year number
            year_number = int(year)
            # Convert the year number to its spoken form
            year_words = year_to_words(year_number)
            # Replace the year number with its spoken form in the text
            text = text.replace(year, year_words)

        # Find all year ranges in the text
        year_ranges = re.findall(r'\b(\d{4})-(\d{4})\b', text)
        for start_year, end_year in year_ranges:
            # Parse the year numbers
            start_year_number = int(start_year)
            end_year_number = int(end_year)
            # Convert the year numbers to their spoken form
            start_year_words = year_to_words(start_year_number)
            end_year_words = year_to_words(end_year_number)
            # Replace the year range with its spoken form in the text
            text = text.replace(f"{start_year}-{end_year}", f"{start_year_words} und {end_year_words}")
        
        # Remove footnote indicators
        #             word      [number] EOL/period/whitespace
        text = re.sub(r'(?<=\w)\[\d+\](?=[\s\.]|$)', '', text)

        # Remove numbers in brackets with three or less digits
        text = re.sub(r'\(\d{1,3}\)', '', text)
        
        # Replace "something: what it is" and "something - it is what it is" with a pause marker
        text = re.sub(r'(\w+): (\w+)', r'\1, \2', text)
        text = re.sub(r'(\w+) - (\w+)', r'\1, \2', text)
        
        # Replace English words with their correct pronunciation
        with open('english_pronunciation_german.json', 'r') as file:
            english_pronunciation_dict = json.load(file)

        for english_word, pronunciation in english_pronunciation_dict.items():
            text = text.replace(english_word, pronunciation)
    
        # Your existing code...
        
    ##### End de-specific code
        
    # Convert numbers to words
    numbers = re.findall(r'\b\d+\b', text)
    for number in numbers:
        text = text.replace(number, num2words(int(number), lang=language))

    # For example, let's just print the converted text for now
    print(f"Converted text: {text} (Language: {language})")
    

def main():
    parser = argparse.ArgumentParser(description='Convert text to TTS-readable words')
    parser.add_argument('text', nargs='?', help='Text string to convert')
    parser.add_argument('-f', '--file', help='Path to a text file')
    parser.add_argument('-t', '--language', help='two-letter string for the language')

    args = parser.parse_args()

    if args.language not in supported_languages:
        print(f"Unsupported language: {args.language}. Supported languages are: {', '.join(supported_languages.keys())}")
        raise SystemExit

    if args.text:
        prepare_text(args.text, args.language)
    elif args.file:
        with open(args.file, 'r') as file:
            text = file.read()
            prepare_text(text, args.language)
    else:
        # Read from stdin
        text = sys.stdin.read()
        prepare_text(text, args.language)

if __name__ == '__main__':
    main()