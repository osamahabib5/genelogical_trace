#!/usr/bin/env python3
"""
Test script for the genealogy agent
"""

import asyncio
import os
import tempfile
from pathlib import Path

# Add the backend directory to Python path
import sys
sys.path.append(str(Path(__file__).parent / "app" / "backend"))

from agent_service import genealogy_agent


async def test_agent():
    """Test the genealogy agent with sample data"""

    # Create a temporary test file
    test_data = """
    John Smith was born on 01/15/1980 in New York City. He married Jane Doe on 06/20/2005.
    They had two children: Michael Smith (born 03/10/2007) and Sarah Smith (born 11/22/2009).
    The family moved to Los Angeles in 2010.
    """

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_data)
        temp_file = f.name

    try:
        print("Testing genealogy agent...")
        result = await genealogy_agent.process_document(temp_file, document_id=999)
        print("Agent result:", result)

    finally:
        # Clean up
        os.unlink(temp_file)


if __name__ == "__main__":
    asyncio.run(test_agent())