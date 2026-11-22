"""commands/completion.py —— Shell completion 脚本输出。

PRD §4.10：输出 bash/zsh/fish 脚本。
用法：
  source <(genie-term completion bash)
  source <(genie-term completion zsh)
  eval "$(genie-term completion fish)"
"""

from __future__ import annotations

import typer

app = typer.Typer(
    name="completion",
    help="生成 shell completion 脚本",
    add_completion=False,
    invoke_without_command=True,
)


# Bash completion template（typer 原生生成 + 我们加一点别名友好）
_BASH_TEMPLATE = """\
# genie-term bash completion
# 安装: source <(genie-term completion bash)
# 永久: genie-term completion bash > ~/.local/share/bash-completion/completions/genie-term

_genie_term_completion() {{
    local IFS=$'\\n'
    local response

    response=$(env COMP_WORDS="${{COMP_WORDS[*]}}" COMP_CWORD=$COMP_CWORD _GENIE_TERM_COMPLETE=bash_complete $1)

    for completion in $response; do
        IFS=',' read -r type value <<< "$completion"
        if [[ $type == 'dir' ]]; then
            COMPREPLY=()
            compopt -o dirnames
        elif [[ $type == 'file' ]]; then
            COMPREPLY=()
            compopt -o default
        elif [[ $type == 'plain' ]]; then
            COMPREPLY+=($value)
        fi
    done

    return 0
}}

complete -F _genie_term_completion genie-term
"""

_ZSH_TEMPLATE = """\
# genie-term zsh completion
# 安装: source <(genie-term completion zsh)

#compdef genie-term

_genie-term_completion() {{
    local -a completions
    local -a completion_choices
    local response

    response=$(env COMP_WORDS="${{(j: :)words}}" COMP_CWORD=$((CURRENT-1)) _GENIE_TERM_COMPLETE=bash_complete $1)

    for completion in ${{(f)response}}; do
        local type value
        type=${{completion%%,*}}
        value=${{completion#*,}}
        if [[ $type == 'plain' ]]; then
            completions+=("$value")
        elif [[ $type == 'file' ]]; then
            _files
            return 0
        elif [[ $type == 'dir' ]]; then
            _dirs
            return 0
        fi
    done

    if [[ -n $completions ]]; then
        _describe 'values' completions
    fi
    return 0
}}

compdef _genie-term_completion genie-term
"""

_FISH_TEMPLATE = """\
# genie-term fish completion
# 安装: genie-term completion fish | source
# 永久: genie-term completion fish > ~/.config/fish/completions/genie-term.fish

function __genie_term_completion
    set -l response
    set -l completions
    set response (env _GENIE_TERM_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -t) genie-term)
    for completion in $response
        set completions $completions $completion
    end
    echo $completions
end

complete -c genie-term -f -a "(__genie_term_completion)"
"""


@app.callback(invoke_without_command=True)
def _callback(
    ctx: typer.Context,
    shell: str = typer.Argument(..., help="Shell 类型: bash|zsh|fish"),
) -> None:
    """输出 shell completion 脚本。"""
    shell = shell.lower()

    if shell == "bash":
        typer.echo(_BASH_TEMPLATE)
    elif shell == "zsh":
        typer.echo(_ZSH_TEMPLATE)
    elif shell == "fish":
        typer.echo(_FISH_TEMPLATE)
    else:
        typer.echo(f"不支持的 shell: {shell}", err=True)
        typer.echo("支持的: bash, zsh, fish", err=True)
        raise typer.Exit(code=2)
