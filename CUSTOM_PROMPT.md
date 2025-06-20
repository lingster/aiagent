Using shelltools and execute_linux_shell_command.

Please use /data as the root folder for this project. 
Firstly check to see if there are AGENTS.md, CLAUDE.md or CONVENTIONS.md file and read them for additional instructions. 

When implementing code please always ensure you use the shelltools and execute_linux_shell_command to do so. 
So write out the code as files via the shelltools and exceute_linux_shell_command to do so. 
When making code changes use write out the complete file using the cat command.

If you have created any temporary or intermediate files, please remember to delete them at the end of the task.

When you have written new code,  please ask me if I want you to write a unit test to verify the code works. If so, please ensure that you have high code coverage. Also code, build, test and iterate to ensure that the code works correctly.

Use SOLID and KISS coding principals. Ensuring that code is reusable and split into modules. 

Try to limit the size of code modules to no more than 300 lines. 

<python_coding_standards>
if there is a .env.local file located in /data then ensure that you have loaded the environment variables contained in the file before running any python scripts.

we are using uv as our python package manager. so you can do:

uv add <packagename> 
to add new packages

and 

uv run python <scriptname> 

to be able to run python scripts.

When writing python code, ensure you use loguru for logging. Use the builtin generic types for typedefs, eg use list instead of List, use dict instead of Dict (ie lowercase instead of captialised).

When writing python use typehints and generic types where possible. Setup and run mypy and ensure all errors are fixed. 

When writing functions, create pydantic types, as opposed to using dict[str, Any] to ensure between type checking, definition and to reduce errors.

use python 3.10 way of typedefs, eg "list[str] | None" instead of "Optional[List[str]]"
</python_coding_standards>

<javascript_coding_standards>
When writing Javascript follow best practices to ensure code is clean, optimised for performance and readable.

</javascript_coding_standards>


<html_coding_standards>
The code is a django project, which uses alpinejs and htmx for the frontend. Where possible use flowbite and tailwindcss for style and components. Please use these libraries and frameworks where possible. When writing html, use semantic elements where possible and minimize the use of div elements to help keep the html code clean and concise.

</html_coding_standards>

When you have completed the task. Can you list out the files that have been created, changed or delete. 
Then for each file output in diff format the changes made. 

If you see the message "failed to run linux command" then please stop what you are doing and ask if the server can be checked before resuming. DO NOT continue until I have confirmed what to do next.

DO NOT make any changes to code until you have confirmed ok with me and suggested 3 or more options or potential solutions. 

ALWAYS  explain the cause and reason for any errors and list out options to resolve. Do not apply any changes until you have asked me which option to use and I have confirmed the solution to use. 

# Slash commands:
The following yaml is a list of slash prompts. If you see a prompt with a word 
starting with the character / and matching the lookup, then replace the 
slash prompt and use this prompt instructions that follow. For example /joke 
result in telling a joke. If there are additional words after the slash 
word then add that to the end of the command instructions. 
For example "/joke about zebras" works tell a dad's joke about zebras.

If the slash command is not listed in the yaml below, assume it is a shell 
command and run that using shelltools after removing the / at the start, 
eg /head CONVENTIONS.md would run the linux command "head CONVENTIONS.md". 
Print out the value of 'output' using bash code block in markdown.

hello:
  - reply with the word world

Joke:
 - tell a dad joke

todo:
 - look for the comments with the words TODO, then follow the instructions contained within the rest of the TODO comment and implement the required code features.

Ofix:
 - list options to fix, but don't do so until I have choose the option

Swot:
 - perform a swot analysis and output the results in a markdown table

Gr:
 - draw a chart using mermaid markdown

why:
 - ultrathink and explain why and list options to fix, but don't apply a fix until I have confirmed

ask:
 - if there are any doubts or ambiguities please ask me for clarification.

summary: 
 - can you give me a summary of the files you modified and a diff please

