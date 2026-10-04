import json
import os
from getpass import getpass
from pathlib import Path

from jev_ultrafast import Agent


def main():
    os.environ["TYPESAFE_API_KEY"] = getpass(
        "Paste your TypeSafe API key: "
    ).strip()

    start_url = (
        "https://ethw.org/Oral-History:List_of_all_Oral_Histories#L"
    )

    goal = (
        "You are starting at the L section of the oral-history index. "
        "Find and open Barbara Liskov's 1991 interview. "
        "Inspect the visible links first, then scroll down if needed. "
        "There are two Barbara Liskov interviews; choose the 1991 one. "
        "Do not use the search box or type text. "
        "Stop when the correct interview page is open. "
        "If a login or verification challenge prevents access, stop as blocked."
    )

    with Agent(start_url, goal) as agent:
        for step in range(1, 16):
            state = agent.command("predict")
            decision = state["decision"]

            print(f"\nStep {step}")
            print("Proposed action:", decision["operation"])
            print("Target:", decision["target"])

            if decision["operation"] == "DONE":
                expected_url = (
                    "https://ethw.org/Oral-History:Barbara_Liskov_(1991)"
                )
                actual_url = state["page"]["url"].split("#", 1)[0]

                if actual_url == expected_url:
                    print("Success: reached the 1991 Liskov interview.")

                    result = {
                        "source_id": "ieee-liskov-1991",
                        "url": actual_url,
                        "title": state["page"]["title"],
                        "method": "jev_guided_browser_navigation",
                        "approved_clicks": True,
                        "verified": True,
                    }

                    Path(
                        "data/processed/browser-result.json"
                    ).write_text(
                        json.dumps(result, indent=2),
                        encoding="utf-8",
                    )
                else:
                    print("JEV reported DONE, but the URL does not match.")
                    print("Actual URL:", actual_url)

                break

            Path(
                f"data/processed/browser-step-{step}.json"
            ).write_text(
                json.dumps(state, indent=2),
                encoding="utf-8",
            )

            if decision["operation"] == "CLICK":
                target = next(
                    (
                        element
                        for element in state["elements"]
                        if element["index"] == decision["target"]
                    ),
                    None,
                )

                if target is None:
                    print("Could not identify the target.")
                    break

                print("Proposed click:", target["label"])
                approval = input("Execute this click? [y/N]: ")

                if approval.strip().lower() != "y":
                    break

            elif decision["operation"] != "SCROLL_DOWN":
                print("Stopping:", decision["operation"])
                break

            state = agent.command(
                "act",
                {"fingerprint": state["page"]["fingerprint"]},
            )

            print("Status after action:", state["status"])

            if state["status"] != "ready":
                print("Agent stopped.")
                break
        else:
            print("Reached the fifteen-scroll limit.")

        Path("data/processed/browser-final-state.json").write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()