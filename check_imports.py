try:
    from note_writer_lab.web import app
    print("Imports successful!")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
