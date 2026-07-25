import os
import sys

# Add backend directory to sys path so we can import things
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from database import SessionLocal
import models
from graph import compile_workflow, run_workflow
import traceback

def run_test():
    db = SessionLocal()
    try:
        # Create a dummy user
        user = models.User(email="test_user@example.com", name="Test User", google_id="dummy_123")
        db.add(user)
        db.commit()
        db.refresh(user)
        
        # Add an API key for the user
        api_key = models.UserApiKey(user_id=user.id, provider="openai", api_key="sk-fake-openai-key-12345")
        db.add(api_key)
        db.commit()
        
        # Create a project
        project = models.Project(user_id=user.id, title="Test Project")
        db.add(project)
        db.commit()
        db.refresh(project)

        # Define a test graph using the API key
        nodes = [
            {
                "id": "node_1",
                "type": "startNode",
                "data": {}
            },
            {
                "id": "node_2",
                "type": "llmNode",
                "data": {
                    "model": "gpt-4o-mini",
                    "apiKey_source": "apicenter",
                    "apiKey": "{{API_CENTER:openai}}",
                    "systemPrompt": "You are a test bot",
                    "userPrompt": "Hello!"
                }
            }
        ]
        edges = [
            {
                "source": "node_1",
                "target": "node_2",
                "sourceHandle": "out",
                "targetHandle": "in"
            }
        ]

        print("--- Test 1: Compiling Workflow with Graph Injection ---")
        # Run workflow
        result, tokens, logs = run_workflow(nodes, edges, db=db, project_id=project.id)
        print("Result:", result)
        print("Logs count:", len(logs))
        
        # The result should contain the dynamic execution error since sk-fake-openai-key-12345 is invalid for real OpenAI,
        # but what matters is that it successfully injected the key and tried to run!
        
        # Let's inspect the compiled code to ensure injection worked
        
        # Reset nodes to original to see compilation directly
        nodes[1]['data']['apiKey'] = "{{API_CENTER:openai}}"
        # Wait, run_workflow modifies nodes in place. Let's reset it.
        nodes[1]['data']['apiKey'] = "{{API_CENTER:openai}}"
        
        print("\n--- Test 2: Checking compiled code ---")
        
        # Simulate injection
        api_keys = db.query(models.UserApiKey).filter(models.UserApiKey.user_id == project.user_id).all()
        api_key_map = {f"{{{{API_CENTER:{k.provider}}}}}": k.api_key for k in api_keys}
        
        def replace_api_keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and v in api_key_map:
                        obj[k] = api_key_map[v]
                    elif isinstance(v, (dict, list)):
                        replace_api_keys(v)
            elif isinstance(obj, list):
                for i in range(len(obj)):
                    if isinstance(obj[i], str) and obj[i] in api_key_map:
                        obj[i] = api_key_map[obj[i]]
                    elif isinstance(obj[i], (dict, list)):
                        replace_api_keys(obj[i])
                        
        replace_api_keys(nodes)
        
        code = compile_workflow(nodes, edges)
        if "api_key=\"sk-fake-openai-key-12345\"" in code:
            print("SUCCESS: API key was successfully injected into compiled code!")
        else:
            print("FAILURE: API key was not found in compiled code.")
            print(code)
            
        print("\n--- Test 3: Missing API Key Fallback ---")
        # What if user didn't register Gemini key but uses Gemini node?
        nodes[1]['data']['model'] = "gemini-1.5-flash"
        nodes[1]['data']['apiKey'] = "{{API_CENTER:gemini}}"
        replace_api_keys(nodes)
        code2 = compile_workflow(nodes, edges)
        # Should just be ChatGoogleGenerativeAI(model="gemini-1.5-flash", max_retries=0, api_key="{{API_CENTER:gemini}}")
        if "{{API_CENTER:gemini}}" in code2:
            print("SUCCESS: Unregistered API key remains as template string.")
        else:
            print("FAILURE: Unregistered API key handling failed.")
            print(code2)

    except Exception as e:
        traceback.print_exc()
    finally:
        # Cleanup
        db.query(models.Project).filter(models.Project.user_id == user.id).delete()
        db.query(models.UserApiKey).filter(models.UserApiKey.user_id == user.id).delete()
        db.query(models.User).filter(models.User.id == user.id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    run_test()
