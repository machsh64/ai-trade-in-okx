"""
AI Chat Service - Unified interface for different AI providers
"""
import logging
import random
import json
import time
from typing import Dict, Optional, List
from letta_client import Letta, MessageCreate, TextContent

import requests


logger = logging.getLogger(__name__)


def chat_with_openai(
    api_key: str,
    base_url: str,
    model: str,
    messages: List[Dict],
    temperature: float = 0.5,
    max_tokens: int = 2500
) -> Optional[str]:
    """
    Chat with OpenAI-compatible API
    
    Args:
        api_key: API key for authentication
        base_url: Base URL of the API endpoint
        model: Model name to use
        messages: List of message dicts with 'role' and 'content'
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens in response
        
    Returns:
        Response text content or None if failed
        
    Example:
        >>> messages = [{"role": "user", "content": "Analyze BTC market"}]
        >>> response = chat_with_openai(
        ...     api_key="sk-xxx",
        ...     base_url="https://api.openai.com/v1",
        ...     model="gpt-4",
        ...     messages=messages
        ... )
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Construct API endpoint URL
        base_url = base_url.rstrip('/')
        api_endpoint = f"{base_url}/chat/completions"
        
        logger.info(f"Calling OpenAI-compatible API: {api_endpoint} (model: {model})")
        
        # Retry logic for rate limiting
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30,
                    verify=False  # Disable SSL verification for custom AI endpoints
                )
                
                if response.status_code == 200:
                    break  # Success, exit retry loop
                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff with jitter
                    logger.warning(f"API rate limited (attempt {attempt + 1}/{max_retries}), waiting {wait_time:.1f}s...")
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"API rate limited after {max_retries} attempts: {response.text}")
                        return None
                else:
                    error_detail = response.text
                    try:
                        error_json = response.json()
                        error_detail = json.dumps(error_json, ensure_ascii=False)
                    except:
                        pass
                    logger.error(f"API returned status {response.status_code}: {error_detail}")
                    return None
            except requests.RequestException as req_err:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {req_err}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"API request failed after {max_retries} attempts: {req_err}")
                    return None
        
        result = response.json()
        
        # Log the full response for debugging
        logger.debug(f"AI API response: {json.dumps(result, ensure_ascii=False)[:500]}...")
        
        # Extract text from OpenAI-compatible response format
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            
            # Check if response was truncated due to length limit
            if finish_reason == "length":
                logger.warning(f"AI response was truncated due to token limit. Consider increasing max_tokens.")
                text_content = message.get("reasoning", "") or message.get("content", "")
            else:
                text_content = message.get("content", "")
            
            if not text_content:
                logger.error(f"Empty content in AI response. Full message: {message}")
                return None
            
            logger.info(f"AI response received successfully, length: {len(text_content)} chars")
            return text_content.strip()
        
        logger.error(f"Unexpected AI response format: {json.dumps(result, ensure_ascii=False)[:500]}...")
        return None
        
    except requests.RequestException as err:
        logger.error(f"OpenAI API request failed: {err}")
        return None
    except json.JSONDecodeError as err:
        logger.error(f"Failed to parse API response as JSON: {err}")
        return None
    except Exception as err:
        logger.error(f"Unexpected error calling OpenAI API: {err}", exc_info=True)
        return None


def chat_with_letta(
    base_url: str,
    token: str,
    agent_id: str,
    messages: str,
    project: Optional[str] = "default-project"
) -> Optional[str]:
    """
    Chat with Letta AI service (for future use with v2.0.0 architecture)
    
    Args:
        base_url: Letta server base URL (e.g., "http://localhost:8080")
        token: Letta API authentication token
        agent_id: Letta agent ID to interact with
        messages: User message text (single string for now, will support list in future)
        project: Optional project ID for multi-project setup
        max_tokens: Maximum tokens in response - reserved for future use
    
    Returns:
        Response text content or None if failed
        
    Note:
        This function is prepared for v2.0.0 architecture upgrade.
        Currently not in use. Requires: pip install letta-client
        
    Example:
        >>> response = chat_with_letta(
        ...     base_url="http://localhost:8080",
        ...     token="your-token",
        ...     agent_id="agent-123",
        ...     messages="Analyze BTC market trend"
        ... )
    
    Letta Features:
        - Core Memory: Long-term strategy principles and risk rules
        - Episodic Memory: Historical trading cases and experiences
        - Session Management: Multi-turn conversation context
        - Agent-based: Intelligent agent decision system
    """
    try:

        
        letta_client = Letta(
            base_url=base_url,
            token=token,
            project=project
        )
        
        # Create message for Letta
        letta_response = letta_client.agents.messages.create(
            agent_id=agent_id,
            messages=[
                MessageCreate(
                    role="user",
                    content=[
                        TextContent(
                            text=messages,
                        )
                    ],
                )
            ],
        )
        
        # Extract response text
        # Note: Adjust this based on actual Letta response format
        if letta_response:
            # Try different possible response formats
            if hasattr(letta_response, 'content'):
                return str(letta_response.content)
            elif hasattr(letta_response, 'text'):
                return str(letta_response.text)
            elif hasattr(letta_response, 'message'):
                return str(letta_response.message)
            elif isinstance(letta_response, dict):
                return letta_response.get('content') or letta_response.get('text') or json.dumps(letta_response)
            else:
                # Fallback: convert to string
                logger.warning(f"Unexpected Letta response format: {type(letta_response)}")
                return str(letta_response)
        
        logger.warning("Empty Letta response received")
        return None
        
    except ImportError:
        logger.error("letta-client not installed. Install with: pip install letta-client")
        return None
    except Exception as err:
        logger.error(f"Letta API error: {err}", exc_info=True)
        return None
