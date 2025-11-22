import csv
import sys

def inspect_tsv(filepath, name):
    print(f"\n--- Inspecting {name} ({filepath}) ---")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            header = next(reader) # Assuming first row is header? Or data?
            # Community notes data usually has headers. Let's check.
            # If the first item is a number, it might be data.
            
            print(f"Row 0 (Potential Header): {header}")
            for i, val in enumerate(header):
                print(f"  [{i}] {val}")
                
            row1 = next(reader)
            print(f"Row 1 (Data): {row1}")
    except Exception as e:
        print(f"Error reading {name}: {e}")

if __name__ == "__main__":
    # inspect_tsv("data/notes-00000.tsv", "Notes")
    
    print("Inspecting unique statuses in noteStatusHistory...")
    statuses = set()
    try:
        with open("data/noteStatusHistory-00000.tsv", 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for i, row in enumerate(reader):
                statuses.add(row.get('currentStatus'))
                if i > 10000:
                    break
    except Exception as e:
        print(e)
        
    print("Unique Statuses:", statuses)
