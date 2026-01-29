import asyncio
import logging
import sys

# Setup logging to see output
logging.basicConfig(level=logging.INFO)

async def test():
    try:
        from automation import generate_payment_link
        print("Import successful")
        # We can't really run it without DB and Client, but let's see if it fails on import or browser launch
    except Exception as e:
        print(f"Import failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
