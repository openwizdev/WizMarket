"""Public GitHub repositories for coding-agent CLIs and agent harnesses not already listed in WizMarket."""
import fetching

NAME = "GitHub public repositories"
PLUGS_INTO = "An agent CLI you run yourself"

# (id, display name, GitHub owner/repo, extra topical tags)
REPOS = [
    ("aider", "Aider", "Aider-AI/aider", ["terminal"]),
    ("plandex", "Plandex", "plandex-ai/plandex", ["terminal"]),
    ("continue-cli", "Continue", "continuedev/continue", ["terminal", "ide"]),
    ("freebuff", "Freebuff", "CodebuffAI/freebuff", ["terminal"]),
    ("forgecode", "ForgeCode", "tailcallhq/forgecode", ["terminal"]),
    ("open-interpreter", "Open Interpreter", "openinterpreter/openinterpreter", ["terminal"]),
    ("gptme", "gptme", "gptme/gptme", ["terminal"]),
    ("swe-agent", "SWE-agent", "SWE-agent/SWE-agent", ["github"]),
    ("mini-swe-agent", "mini-swe-agent", "SWE-agent/mini-swe-agent", ["terminal"]),
    ("amazon-q-developer-cli", "Amazon Q Developer CLI", "aws/amazon-q-developer-cli", ["terminal"]),
    ("trae-agent", "Trae Agent", "bytedance/trae-agent", ["terminal"]),
    ("groq-code-cli", "Groq Code CLI", "build-with-groq/groq-code-cli", ["terminal"]),
    ("letta-code", "Letta Code", "letta-ai/letta-code", ["terminal"]),
    ("kode-cli", "Kode CLI", "shareAI-lab/Kode-CLI", ["terminal"]),
    ("nanocoder", "Nanocoder", "Nano-Collective/nanocoder", ["terminal"]),
    ("iflow-cli", "iFlow CLI", "iflow-ai/iflow-cli", ["terminal"]),
    ("every-code", "Every Code", "just-every/code", ["terminal"]),
    ("claude-squad", "Claude Squad", "smtg-ai/claude-squad", ["terminal", "tmux"]),
    ("qodo-command", "Qodo Command", "qodo-ai/command", ["terminal"]),
    ("grok-cli", "Grok CLI", "superagent-ai/grok-cli", ["terminal"]),
    ("ra-aid", "RA.Aid", "ai-christianson/RA.Aid", ["terminal"]),
    ("octofriend", "Octofriend", "synthetic-lab/octofriend", ["terminal"]),
    ("toad", "Toad", "batrachianai/toad", ["terminal"]),
    ("vibe-kanban", "Vibe Kanban", "BloopAI/vibe-kanban", ["orchestration"]),
    ("agent-zero", "Agent Zero", "agent0ai/agent-zero", ["framework"]),
    ("code-puppy", "Code Puppy", "mpfaffenberger/code_puppy", ["terminal"]),
    ("neovate-code", "Neovate Code", "neovateai/neovate-code", ["terminal"]),
    ("devika", "Devika", "stitionai/devika", ["autonomous"]),
    ("coder-xum", "Coder Xum", "coder/xum", ["desktop"]),
    ("crystal-nimbalyst", "Crystal (Nimbalyst)", "stravu/crystal", ["desktop", "worktrees"]),
    ("sculptor", "Sculptor", "imbue-ai/sculptor", ["orchestration"]),
    ("happy-cli", "Happy", "slopus/happy", ["orchestration"]),
    ("opcode", "Opcode", "winfunc/opcode", ["desktop"]),
    ("deepagents", "Deep Agents", "langchain-ai/deepagents", ["framework"]),
    ("open-swe", "Open SWE", "langchain-ai/open-swe", ["github"]),
    ("devon", "Devon", "entropy-research/Devon", ["terminal"]),
    ("auto-code-rover", "AutoCodeRover", "AutoCodeRoverSG/auto-code-rover", ["github"]),
    ("aider-desk", "AiderDesk", "magiksoft/aider-desk", ["desktop"]),
    ("dyad", "Dyad", "dyad-sh/dyad", ["desktop"]),
    ("ironclaw", "IronClaw", "nearai/ironclaw", ["runtime"]),
    ("humanlayer", "HumanLayer", "humanlayer/humanlayer", ["approvals"]),
    ("claude-task-master", "Claude Task Master", "eyaltoledano/claude-task-master", ["planning"]),
    ("ntm", "Named Tmux Manager", "Dicklesworthstone/ntm", ["tmux", "orchestration"]),
    ("cmux", "cmux", "manaflow-ai/cmux", ["terminal"]),
    ("claude-agent-sdk-python", "Claude Agent SDK (Python)", "anthropics/claude-agent-sdk-python", ["sdk"]),
    ("openai-agents-python", "OpenAI Agents SDK (Python)", "openai/openai-agents-python", ["sdk"]),
    ("mcp-agent", "mcp-agent", "lastmile-ai/mcp-agent", ["sdk", "mcp"]),
    ("agentops", "AgentOps", "AgentOps-AI/agentops", ["observability"]),
    ("aichat", "AIChat", "sigoden/aichat", ["terminal"]),
    ("llm-cli", "LLM", "simonw/llm", ["terminal"]),
    ("mods", "Mods", "charmbracelet/mods", ["terminal"]),
    ("shell-gpt", "ShellGPT", "TheR1D/shell_gpt", ["terminal"]),
]


def fetch():
    facts = fetching.repos([repo for _, _, repo, _ in REPOS])
    entries = []
    for listing_id, name, full_name, extra_tags in REPOS:
        info = facts.get(full_name)
        if not info:
            continue
        entries.append({
            "id": listing_id,
            "name": name,
            "source_description": info["description"],
            "url": info["url"],
            "licence": info["licence"],
            "licence_url": info["licence_url"],
            "source_url": info["url"],
            "tags": ["coding-agent-cli", *extra_tags],
            "plugs_into": PLUGS_INTO,
        })
    return entries
