# Interview walkthrough

1. Explain the customer problem: support replies need policy context and human judgment.
2. Run the local model, API, and worker. Submit the synthetic returns request.
3. Show queue state, rule-based intent, retrieved policies, cited JSON draft, model/prompt metadata, and trace.
4. Explain that allowed citations do not verify facts. Edit unsupported wording before approving.
5. Show the approval event; no email is sent.
6. Discuss idempotent submission, optimistic review conflicts, atomic claims, retries, and lease fencing.
7. Walk through the 15 integration cases and 12 synthetic retrieval cases. Separate retrieval evaluation from LLM answer quality.
8. Explain extension choices: a larger evaluated model, held-out data with permission, improved semantic verification, SSO, durable service queue/database, retention, and load tests.

This project demonstrates Python API design, SQL indexing, provider abstraction, structured-output validation, asynchronous execution, concurrency, authentication, testing, and operations. It was built in November 2026. Do not claim autonomous email delivery, trained intent classification, vector embeddings, production adoption, or an AWS deployment.
