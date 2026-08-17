"""
Agent service for automatic data cleaning and processing
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
import re

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_community.llms import Ollama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from database import SessionLocal, Document, DocumentChunk, AncestryData, DocumentFootnote
from document_processor import DocumentProcessor
from embedding_service import embedding_service
from config import settings

logger = logging.getLogger(__name__)


class DataCleaningTool(BaseTool):
    """Tool for cleaning and normalizing genealogical data"""

    name: str = "data_cleaner"
    description: str = "Clean and normalize genealogical data from uploaded documents"

    def _run(self, data: str) -> str:
        """Clean the provided data"""
        try:
            # Parse JSON if it's JSON data
            if data.strip().startswith('{') or data.strip().startswith('['):
                parsed_data = json.loads(data)
                return self._clean_json_data(parsed_data)
            else:
                return self._clean_text_data(data)
        except json.JSONDecodeError:
            return self._clean_text_data(data)

    def _clean_text_data(self, text: str) -> str:
        """Clean text data by normalizing formatting and extracting entities"""
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', text.strip())

        # Fix common OCR errors in genealogical data
        cleaned = re.sub(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b', r'\1/\2/\3', cleaned)  # Normalize dates
        cleaned = re.sub(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', r'\2/\3/\1', cleaned)  # Convert YYYY-MM-DD to MM/DD/YYYY

        return cleaned

    def _clean_json_data(self, data: Any) -> str:
        """Clean JSON data by normalizing structure"""
        if isinstance(data, dict):
            # Normalize person records
            if 'name' in data or 'person' in data:
                return json.dumps(self._normalize_person_record(data), indent=2)
            return json.dumps(data, indent=2)
        elif isinstance(data, list):
            cleaned_items = []
            for item in data:
                if isinstance(item, dict):
                    cleaned_items.append(self._normalize_person_record(item))
                else:
                    cleaned_items.append(item)
            return json.dumps(cleaned_items, indent=2)
        return json.dumps(data, indent=2)

    def _normalize_person_record(self, record: Dict) -> Dict:
        """Normalize a person record structure"""
        normalized = {}

        # Normalize name fields
        name_fields = ['name', 'full_name', 'person_name', 'first_name', 'last_name']
        for field in name_fields:
            if field in record and record[field]:
                normalized['name'] = record[field].strip().title()
                break

        # Normalize date fields
        date_fields = ['birth_date', 'death_date', 'birth', 'death']
        for field in date_fields:
            if field in record and record[field]:
                normalized[field] = self._normalize_date(str(record[field]))

        # Normalize location fields
        location_fields = ['birth_location', 'death_location', 'birth_place', 'death_place']
        for field in location_fields:
            if field in record and record[field]:
                normalized[field] = record[field].strip().title()

        # Copy other fields
        for key, value in record.items():
            if key not in normalized and key not in name_fields + date_fields + location_fields:
                normalized[key] = value

        return normalized

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date string to MM/DD/YYYY format"""
        date_str = date_str.strip()

        # Try different date formats
        patterns = [
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', r'\1/\2/\3'),  # MM/DD/YYYY
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', r'\2/\3/\1'),  # YYYY-MM-DD to MM/DD/YYYY
            (r'(\d{1,2})-(\d{1,2})-(\d{4})', r'\1/\2/\3'),  # MM-DD-YYYY
        ]

        for pattern, replacement in patterns:
            match = re.search(pattern, date_str)
            if match:
                return re.sub(pattern, replacement, date_str)

        return date_str


class DatabaseStorageTool(BaseTool):
    """Tool for storing cleaned data in the database"""

    name: str = "database_storage"
    description: str = "Store cleaned genealogical data in the PostgreSQL database"

    def _run(self, cleaned_data: str, document_id: int) -> str:
        """Store the cleaned data in the database"""
        try:
            db = SessionLocal()
            try:
                # Parse the cleaned data
                if cleaned_data.strip().startswith('{') or cleaned_data.strip().startswith('['):
                    data = json.loads(cleaned_data)
                else:
                    data = {'text': cleaned_data}

                # Store based on data type
                if isinstance(data, dict):
                    self._store_person_record(db, data, document_id)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            self._store_person_record(db, item, document_id)

                db.commit()
                return f"Successfully stored cleaned data for document {document_id}"

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error storing data: {e}")
            return f"Error storing data: {str(e)}"

    def _store_person_record(self, db, record: Dict, document_id: int):
        """Store a person record in the database"""
        # Generate embedding for the record
        text_content = json.dumps(record)
        embedding = embedding_service.embed_text(text_content)

        ancestry_record = AncestryData(
            document_id=document_id,
            person_name=record.get('name', ''),
            birth_date=record.get('birth_date'),
            birth_location=record.get('birth_location'),
            death_date=record.get('death_date'),
            death_location=record.get('death_location'),
            occupation=record.get('occupation'),
            raw_text=text_content,
            embedding=embedding
        )
        db.add(ancestry_record)


class DataQualityAssessmentTool(BaseTool):
    """Tool for assessing data quality and making processing decisions"""

    name: str = "quality_assessor"
    description: str = "Assess the quality of uploaded data and determine processing strategy"

    def _run(self, data: str) -> str:
        """Assess data quality"""
        assessment = {
            'quality_score': 0,
            'issues': [],
            'recommendations': []
        }

        # Check for completeness
        if len(data.strip()) < 10:
            assessment['issues'].append('Data too short')
            assessment['quality_score'] -= 20

        # Check for structured data
        if data.strip().startswith('{') or data.strip().startswith('['):
            try:
                parsed = json.loads(data)
                assessment['quality_score'] += 30
                assessment['recommendations'].append('Structured JSON data detected - will normalize fields')
            except:
                assessment['issues'].append('Invalid JSON structure')

        # Check for genealogical content
        genealogical_keywords = ['birth', 'death', 'marriage', 'census', 'ancestor', 'family']
        found_keywords = [kw for kw in genealogical_keywords if kw.lower() in data.lower()]
        if found_keywords:
            assessment['quality_score'] += len(found_keywords) * 5
            assessment['recommendations'].append(f'Found genealogical keywords: {", ".join(found_keywords)}')

        # Check for dates
        date_pattern = r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b'
        dates = re.findall(date_pattern, data)
        if dates:
            assessment['quality_score'] += len(dates) * 3
            assessment['recommendations'].append(f'Found {len(dates)} potential date references')

        # Overall assessment
        if assessment['quality_score'] >= 50:
            assessment['recommendations'].append('High quality data - proceed with standard processing')
        elif assessment['quality_score'] >= 20:
            assessment['recommendations'].append('Medium quality data - apply cleaning and normalization')
        else:
            assessment['recommendations'].append('Low quality data - requires manual review')

        return json.dumps(assessment, indent=2)


class GenealogyAgent:
    """Agent for automatic genealogical data processing"""

    def __init__(self):
        self.llm = self._get_llm()
        self.tools = [
            DataCleaningTool(),
            DatabaseStorageTool(),
            DataQualityAssessmentTool()
        ]
        self.agent = self._create_agent()
        self.executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=6,
            max_execution_time=300
        )

    def _get_llm(self):
        """Get the appropriate LLM based on configuration"""
        if settings.llm_provider == "openai":
            return ChatOpenAI(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                temperature=0.1
            )
        elif settings.llm_provider == "deepseek":
            # DeepSeek exposes an OpenAI-compatible API
            return ChatOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
                temperature=0.1,
                max_tokens=2048,
                request_timeout=180,
                max_retries=2
            )
        elif settings.llm_provider == "groq":
            return ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0.1
            )
        elif settings.llm_provider == "ollama":
            return Ollama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_chat_model,
                temperature=0.1
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    def _create_agent(self):
        """Create the agent with tools"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert genealogical data processing agent. Your task is to:

1. Analyze uploaded genealogical data
2. Assess its quality and structure
3. Clean and normalize the data
4. Extract genealogical entities (people, dates, locations, relationships)
5. Store the cleaned data in the database

Always use the available tools in this order:
1. First, assess data quality with quality_assessor
2. Then clean the data with data_cleaner
3. Finally, store the cleaned data with database_storage

Be thorough and ensure data integrity. For genealogical data, pay special attention to:
- Name normalization (proper capitalization)
- Date format standardization (MM/DD/YYYY)
- Location standardization
- Relationship extraction
- Data completeness"""),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Use different agent creation based on LLM provider
        if settings.llm_provider in ["openai", "groq", "deepseek"]:
            return create_openai_tools_agent(self.llm, self.tools, prompt)
        else:
            # For Ollama, use a simpler approach
            from langchain.agents import create_react_agent
            from langchain_core.prompts import PromptTemplate

            ollama_prompt = PromptTemplate.from_template("""You are an expert genealogical data processing agent. Your task is to analyze uploaded genealogical data, assess its quality, clean and normalize it, extract genealogical entities, and store the cleaned data in the database.

You have access to the following tools:
{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought: {agent_scratchpad}
""")

            return create_react_agent(self.llm, self.tools, ollama_prompt)

    async def process_document(self, file_path: str, document_id: int) -> Dict[str, Any]:
        """Process a document using the agent"""
        try:
            # Extract text from the document
            file_ext = Path(file_path).suffix.lower()
            if file_ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == '.json':
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    content = json.dumps(data, indent=2)
            else:
                # Use existing document processor for other formats
                full_text, _ = DocumentProcessor.process_document(file_path)
                content = full_text

            # Run the agent
            logger.info(f"Agent processing document {document_id} ({len(content)} chars)...")
            result = await self.executor.ainvoke({
                "input": f"Process this genealogical data and store it in the database for document {document_id}:\n\n{content}"
            })
            logger.info(f"Agent finished document {document_id}: {str(result.get('output', ''))[:200]}")

            return {
                "success": True,
                "document_id": document_id,
                "agent_output": result.get("output", ""),
                "processed_content": content[:500] + "..." if len(content) > 500 else content
            }

        except Exception as e:
            logger.error(f"Agent processing failed: {e}")
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e)
            }


# Global agent instance
genealogy_agent = GenealogyAgent()