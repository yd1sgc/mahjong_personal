import sys
import types
import inspect

# Mock streamlit if not installed
if "streamlit" not in sys.modules:
    mock_st = types.ModuleType("streamlit")
    mock_st.secrets = {"local_mode": True}
    mock_st.cache_data = lambda *args, **kwargs: (lambda f: f)
    mock_st.session_state = {}
    sys.modules["streamlit"] = mock_st

import traceback

def run():
    tests = []
    
    # 1. test_identity_schema
    import test_identity_schema
    for attr in dir(test_identity_schema):
        if attr.startswith("test_"):
            tests.append((f"test_identity_schema.{attr}", getattr(test_identity_schema, attr)))
            
    # 2. test_supabase_sync
    import test_supabase_sync
    for attr in dir(test_supabase_sync):
        if attr.startswith("test_"):
            tests.append((f"test_supabase_sync.{attr}", getattr(test_supabase_sync, attr)))

    # 3. test_calc
    import test_calc
    for attr in dir(test_calc):
        obj = getattr(test_calc, attr)
        if inspect.isclass(obj) and attr.startswith("Test"):
            instance = obj()
            for m in dir(instance):
                if m.startswith("test_"):
                    tests.append((f"test_calc.{attr}.{m}", getattr(instance, m)))
        elif attr.startswith("test_"):
            tests.append((f"test_calc.{attr}", obj))

    passed = 0
    failed = 0
    print(f"Running {len(tests)} tests...\n")
    for name, func in tests:
        try:
            func()
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\nResult: {passed} passed, {failed} failed.")
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run()
