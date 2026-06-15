import asyncio
import os
import sys

# Add project root to sys.path to resolve imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.local_matcher import sync_deck_locally, load_and_compute_descriptors

async def main():
    demo_list = "1 Godo, Bandit Warlord\n1 Helm of the Host\n1 Sol Ring\n1 Black Lotus\n1 Mountain"
    print("Offline Local Matcher: Pre-syncing default demo card templates...")
    try:
        synced = await sync_deck_locally(demo_list)
        print(f"Successfully synced: {synced}")
        load_and_compute_descriptors()
        print("Demo card templates pre-computed and loaded in memory!")
    except Exception as e:
        print(f"Error during pre-sync: {e}")

if __name__ == "__main__":
    asyncio.run(main())
