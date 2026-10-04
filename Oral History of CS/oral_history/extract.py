"""JEV assesses a quotation; it does not establish historical truth."""
import os
from getpass import getpass
from typesafe_sdk import TypeSafeClient, Noul

QUESTION = "Does this passage describe the speaker's own contribution to computing?"
_api_key = None


def question_for(evidence):
    question = evidence.get("question", QUESTION)
    if not isinstance(question, str) or not question.strip():
        raise ValueError("The evaluation question must be nonempty text.")
    return question


def evaluate_evidence(evidence):
    # Asks JEV to score the quotation against its evaluation question
    global _api_key

    if _api_key is None:
        _api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not _api_key:
            _api_key = getpass("Paste your TypeSafe API key: ").strip()
    client = TypeSafeClient(api_key=_api_key)

    return client.system_one(
        state={"speaker": evidence["speaker"], "passage": evidence["quote"]},
        questions={"describes_own_contribution": Noul(instructions=question_for(evidence))},
    )
