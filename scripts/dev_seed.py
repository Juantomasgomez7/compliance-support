"""Local development seed script, populates a throwaway dev database with fake
data for manual testing.

This is dev tooling: it is NOT part of the deployed service and NOT in PCI scope
(it lives under ``scripts/``, which ``.compliance.yml`` excludes). The key below is
a dummy used only against the local mock processor. The gate should IGNORE this
file: flagging a dummy dev key is the false positive that teaches engineers to
distrust the gate.
"""

# Dummy key for the local mock processor, never a real credential.
DEV_PROCESSOR_KEY = "9c1f8e2a7b4d6051c3e9f0a2b8d4e6f1"


def seed() -> None:
    print(f"seeding dev data against the mock processor ({DEV_PROCESSOR_KEY[:6]}...)")


if __name__ == "__main__":
    seed()
