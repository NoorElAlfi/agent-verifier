# Authorization: "MAY the agent do this?" Static permission rules only. Whether the action is a
# good idea (scope drift, provenance) is verification's job (Agent B), never this file's.
#
# input: {tool, target, params, allowed_tools, max_file_bytes, content_bytes}
#   content_bytes is the UTF-8 size of params.content, computed by the Python wrapper (Rego has
#   no byte-length builtin). Nothing in input comes from agent_claims.
# output: data.av.authz.result = {allow: bool, reasons: [string]}
package av.authz

import rego.v1

path_tools := {"list_files", "read_file", "write_file", "delete_file"}

# every path-like string the call names (submit and run_tests have none)
paths contains p if {
	input.tool in path_tools
	p := input.params.path
}

paths contains input.target if input.tool in path_tools

deny contains "path is not a string" if {
	some p in paths
	not is_string(p)
}

segments(p) := [lower(s) | some s in split(replace(p, "\\", "/"), "/")]

deny contains msg if {
	not input.tool in input.allowed_tools
	msg := sprintf("tool %v is not allowed for this task", [input.tool])
}

deny contains msg if {
	some p in paths
	p == ""
	msg := "empty path"
}

deny contains msg if {
	some p in paths
	startswith(p, "/")
	msg := sprintf("absolute path denied: %v", [p])
}

deny contains msg if {
	some p in paths
	regex.match(`^[A-Za-z]:`, p)
	msg := sprintf("absolute (drive) path denied: %v", [p])
}

deny contains msg if {
	some p in paths
	startswith(p, "~")
	msg := sprintf("home-relative path denied: %v", [p])
}

deny contains msg if {
	some p in paths
	contains(p, "\\")
	msg := sprintf("backslash in path denied: %v", [p])
}

deny contains msg if {
	some p in paths
	contains(p, "\u0000")
	msg := "NUL byte in path denied"
}

deny contains msg if {
	some p in paths
	".." in segments(p)
	msg := sprintf("path escapes the repo root (..): %v", [p])
}

deny contains msg if {
	some p in paths
	".git" in segments(p)
	msg := sprintf(".git is off limits: %v", [p])
}

deny contains msg if {
	input.tool == "write_file"
	input.content_bytes > input.max_file_bytes
	msg := sprintf("file too large: %v bytes > %v", [input.content_bytes, input.max_file_bytes])
}

result := {"allow": count(deny) == 0, "reasons": sort([m | some m in deny])}
