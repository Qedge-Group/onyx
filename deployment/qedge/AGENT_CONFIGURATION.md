# QEdge embedded Agent configuration

The widget reads its welcome questions from the selected Onyx Agent. Set the display name and submitted message in Conversation Starters. An empty list displays no welcome questions. The list refreshes when the widget mounts or its scope changes. Existing open widgets need a reload to pick up later edits.

The Demo scope form shows effective behavior without exposing prompt text. Instructions and Reminders apply to grounded answer synthesis. They do not filter raw search results. Document sets and the server business policy enforce that boundary. Question language and a configured site summary model override conflicting Agent settings. Evidence and citation rules stay mandatory. The custom route does not inject the current date.

`repair_agent_instructions.py` aligns the saved language guidance with the owner's question-language preference. It completes the known incomplete CN citation section. It checks the expected Agent names, saves the previous prompt values, and preserves starters and document-set bindings. Run it once inside the backend container with `PYTHONPATH=/app`. Copy the printed backup path to the deployment archive before replacing the container. Repeating the repair preserves the same resulting text.
