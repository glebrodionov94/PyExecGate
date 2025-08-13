def greet(name: str, times: int = 1):
    return {"message": " ".join([f"Hello, {name}!" for _ in range(times)])}