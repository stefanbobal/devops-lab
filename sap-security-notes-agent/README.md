# SAP Security Notes Agent

MVP flow:

SAP for Me
-> SAPNoteSet
-> filter by system number
-> CVSS / priority evaluation
-> PostgreSQL history
-> future Teams / AI integration

Do not commit:

- SAP credentials
- session cookies
- CSRF tokens
- company system numbers
- production payloads
