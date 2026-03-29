from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq


FALLBACK_COOLDOWN_SECONDS = 300
_fallback_until_ts = 0.0


def _load_local_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


class LLMService:
    def __init__(self) -> None:
        global _fallback_until_ts
        _load_local_env()
        self.api_key = os.getenv('GPT_OSS', '').strip()
        self.primary_model = 'llama-3.1-8b-instant'  # Fast model for normal use
        self.fallback_model = 'llama-3.3-70b-versatile'  # More capable when rate limited
        start_model = self.fallback_model if time.time() < _fallback_until_ts else self.primary_model

        if self.api_key:
            self.llm = ChatGroq(
                api_key=self.api_key,
                model=start_model,
                temperature=0.1,
                max_tokens=4000
            )
            self.enabled = True
            self.current_model = start_model
        else:
            self.llm = None
            self.enabled = False
            self.current_model = None

    def _switch_to_fallback_model(self) -> None:
        """Switch to fallback model when rate limit is hit."""
        global _fallback_until_ts
        if self.current_model == self.primary_model:
            print(f"Switching from {self.primary_model} to fallback model {self.fallback_model} due to rate limit")
            _fallback_until_ts = time.time() + FALLBACK_COOLDOWN_SECONDS
            self.llm = ChatGroq(
                api_key=self.api_key,
                model=self.fallback_model,
                temperature=0.1,
                max_tokens=4000
            )
            self.current_model = self.fallback_model

    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if the error is a rate limit error."""
        error_str = str(error).lower()
        error_message = getattr(error, 'message', '').lower() if hasattr(error, 'message') else ''
        
        # Check various ways rate limits might be reported
        rate_limit_indicators = [
            'rate limit', '429', 'quota exceeded', 'too many requests',
            'rate_limit_exceeded', 'requests per minute', 'rpm', 'tpm'
        ]
        
        return any(indicator in error_str or indicator in error_message for indicator in rate_limit_indicators)

    def test_fallback_mechanism(self) -> str:
        """Test method to demonstrate fallback mechanism."""
        original_model = self.current_model
        print(f"Original model: {original_model}")
        
        # Simulate rate limit error
        fake_error = Exception("Rate limit exceeded")
        if self._is_rate_limit_error(fake_error):
            self._switch_to_fallback_model()
            print(f"Switched to fallback model: {self.current_model}")
            return f"Successfully switched from {original_model} to {self.current_model}"
        else:
            return "Rate limit detection failed"

    def explain_lines(self, language: str, filename: str, lines: list[str]) -> list[dict[str, Any]] | None:
        if not self.enabled:
            return None

        try:
            all_explanations = []

            for idx, line in enumerate(lines, start=1):
                # Small delay to avoid rate limiting
                if idx > 1:
                    import time
                    time.sleep(0.1)
                    
                # Escape quotes in the line for JSON
                escaped_line = line.replace('"', '\\"')
                
                prompt = f'''Analyze this Python code line and return JSON:

Line {idx}: {line}

Return ONLY this JSON object:
{{
    "line": {idx},
    "given_line": "{escaped_line}",
    "what_is_this_line": "brief description",
    "breakdown": "markdown table",
    "related_to_code": "why needed",
    "where_from": "source"
}}'''

                try:
                    response = self.llm.invoke(prompt)
                    result_text = response.content.strip()
                    
                    # Remove markdown code blocks if present
                    if result_text.startswith('```json'):
                        result_text = result_text[7:]
                    if result_text.endswith('```'):
                        result_text = result_text[:-3]
                    result_text = result_text.strip()
                    
                    # Try to extract just the JSON object from the response
                    # Look for the first { and last }
                    start_idx = result_text.find('{')
                    end_idx = result_text.rfind('}')
                    
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        json_text = result_text[start_idx:end_idx+1]
                        try:
                            explanation = json.loads(json_text)
                            if isinstance(explanation, dict):
                                all_explanations.append(explanation)
                                continue  # Skip to next line
                        except json.JSONDecodeError as e:
                            print(f"JSON decode error for line {idx}: {e}")
                            print(f"JSON text: {json_text[:200]}...")
                    
                    # Fallback if JSON parsing failed
                    all_explanations.append({
                        "line": idx,
                        "given_line": line,
                        "what_is_this_line": f"Code line: {line}",
                        "breakdown": "Basic syntax",
                        "related_to_code": "Program execution",
                        "where_from": "Source code"
                    })

                except Exception as line_error:
                    # Check if it's a rate limit error for this specific line
                    if self._is_rate_limit_error(line_error) and self.current_model == self.primary_model:
                        print(f"Rate limit hit for line {idx}, switching to fallback model")
                        self._switch_to_fallback_model()
                        # Retry this specific line with the fallback model
                        try:
                            response = self.llm.invoke(prompt)
                            result_text = response.content.strip()
                            
                            if result_text.startswith('```json'):
                                result_text = result_text[7:]
                            if result_text.endswith('```'):
                                result_text = result_text[:-3]
                            result_text = result_text.strip()
                            
                            start_idx = result_text.find('{')
                            end_idx = result_text.rfind('}')
                            
                            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                json_text = result_text[start_idx:end_idx+1]
                                try:
                                    explanation = json.loads(json_text)
                                    if isinstance(explanation, dict):
                                        all_explanations.append(explanation)
                                        continue
                                except json.JSONDecodeError as e2:
                                    print(f"JSON decode error for line {idx} (fallback): {e2}")
                            
                            # Fallback if JSON parsing failed
                            all_explanations.append({
                                "line": idx,
                                "given_line": line,
                                "what_is_this_line": f"Code line: {line}",
                                "breakdown": "Basic syntax",
                                "related_to_code": "Program execution",
                                "where_from": "Source code"
                            })
                            continue
                        except Exception as fallback_error:
                            print(f"Fallback model also failed for line {idx}: {fallback_error}")
                    
                    # If not rate limit or fallback failed, use basic fallback
                    print(f"LLM failed for line {idx}: {line_error}")
                    all_explanations.append({
                        "line": idx,
                        "given_line": line,
                        "what_is_this_line": f"Code line: {line}",
                        "breakdown": "Basic syntax",
                        "related_to_code": "Program execution",
                        "where_from": "Source code"
                    })

            return all_explanations

        except Exception as e:
            print(f"LLM explain_lines failed: {e}")
            # Check if it's a rate limit error and we haven't switched to fallback yet
            if self._is_rate_limit_error(e) and self.current_model == self.primary_model:
                print("Rate limit hit, switching to fallback model for all lines")
                self._switch_to_fallback_model()
                # Retry all lines with fallback model
                try:
                    all_explanations = []
                    for idx, line in enumerate(lines, start=1):
                        if idx > 1:
                            import time
                            time.sleep(0.2)  # Longer delay for fallback
                            
                        escaped_line = line.replace('"', '\\"')
                        prompt = f'''Analyze this Python code line and return JSON:

Line {idx}: {line}

Return ONLY this JSON object:
{{
    "line": {idx},
    "given_line": "{escaped_line}",
    "what_is_this_line": "brief description",
    "breakdown": "markdown table",
    "related_to_code": "why needed",
    "where_from": "source"
}}'''

                        response = self.llm.invoke(prompt)
                        result_text = response.content.strip()
                        
                        if result_text.startswith('```json'):
                            result_text = result_text[7:]
                        if result_text.endswith('```'):
                            result_text = result_text[:-3]
                        result_text = result_text.strip()
                        
                        start_idx = result_text.find('{')
                        end_idx = result_text.rfind('}')
                        
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            json_text = result_text[start_idx:end_idx+1]
                            try:
                                explanation = json.loads(json_text)
                                if isinstance(explanation, dict):
                                    all_explanations.append(explanation)
                                    continue
                            except json.JSONDecodeError as e2:
                                print(f"JSON decode error for line {idx} (fallback): {e2}")
                        
                        all_explanations.append({
                            "line": idx,
                            "given_line": line,
                            "what_is_this_line": f"Code line: {line}",
                            "breakdown": "Basic syntax",
                            "related_to_code": "Program execution",
                            "where_from": "Source code"
                        })
                    
                    return all_explanations
                    
                except Exception as e2:
                    print(f"Fallback model also failed: {e2}")
            
            # Final fallback
            return [{
                "line": i + 1,
                "given_line": line,
                "what_is_this_line": f"Code line: {line}",
                "breakdown": "Basic syntax",
                "related_to_code": "Program logic",
                "where_from": "User code"
            } for i, line in enumerate(lines)]

    def build_better_architecture(
        self,
        filename: str,
        analysis: dict[str, Any],
        code: str,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        try:
            prompt = f'''
            File: {filename}
            Analysis: {json.dumps(analysis)}
            Code: {code[:1000]}

            Generate a UML class diagram or flowchart for this code.
            Return JSON: {{"layers": [...], "diagram_mermaid": "mermaid syntax", "notes": [...]}}
            '''

            response = self.llm.invoke(prompt)
            result_text = response.content.strip()

            # Try to parse JSON from response
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                # Fallback to manual generation
                return self._manual_architecture(analysis)

        except Exception as e:
            # Check if it's a rate limit error and we haven't switched to fallback yet
            if self._is_rate_limit_error(e) and self.current_model == self.primary_model:
                print(f"Rate limit hit in architecture generation, switching to fallback model")
                self._switch_to_fallback_model()
                # Retry with fallback model
                try:
                    response = self.llm.invoke(prompt)
                    result_text = response.content.strip()
                    try:
                        return json.loads(result_text)
                    except json.JSONDecodeError:
                        return self._manual_architecture(analysis)
                except Exception as e2:
                    print(f"Fallback model also failed for architecture: {e2}")
            
            return self._manual_architecture(analysis)

    def _manual_architecture(self, analysis: dict[str, Any]) -> dict[str, Any]:
        '''Fallback manual architecture generation'''
        functions = analysis.get("functions", [])
        function_details = analysis.get("function_details", {})
        classes = analysis.get("classes", [])
        
        if functions or classes:
            lines = ["classDiagram"]
            for func in functions:
                details = function_details.get(func, {})
                params = details.get("params", [])
                computations = details.get("computations", [])
                lines.append(f"class {func} {{")
                for param in params:
                    lines.append(f"  +{param}: parameter")
                for comp in computations:
                    lines.append(f"  +{comp}: computation")
                lines.append(f"  +{func}({', '.join(params)})")
                lines.append("}")
            diagram = "\\n".join(lines)
        else:
            diagram = "flowchart TD\\nA[Start] --> B[Process] --> C[End]"
        
        return {
            'layers': [{"id": "main", "title": "Components", "detail": f"Functions: {len(functions)}, Classes: {len(classes)}"}],
            'diagram_mermaid': diagram,
            'notes': ["Generated with agent framework"],
        }
