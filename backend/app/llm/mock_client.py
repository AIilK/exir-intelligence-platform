class MockLLMClient:

    def generate(
        self,
        prompt: str,
    ) -> str:

        return """
SELECT TOP 100
    [id],
    [name],
    [city],
    [phone]
FROM [dbo].[customers]
WHERE [city] = N'تهران';
"""