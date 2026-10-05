import uuid

def generate_callid() -> str:
    return f"call_{uuid.uuid4().hex[:8]}"

def clean_schema(schema: dict) -> dict:
    schema.pop("title", None)

    for value in schema.values():
        if isinstance(value, dict):
            clean_schema(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    clean_schema(item)

    return schema