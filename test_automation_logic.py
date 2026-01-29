import asyncio
import logging
import sys

# Setup logging to see output
logging.basicConfig(level=logging.INFO)

async def test():
    try:
        from automation import automate_payment_flow
        print("Import successful")
        # We can't really run it fully without DB and Client
    except Exception as e:
        print(f"Import failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
