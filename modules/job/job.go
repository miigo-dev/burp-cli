package job

import (
	"encoding/json"
	"fmt"
	"os"
)

// Spec describes a single scan job handed to burp-cli by an external
// orchestrator (e.g. a script that reads a Google Sheets row). It carries
// no scan-depth field on purpose: depth is enforced in code, not read from
// the job file.
type Spec struct {
	ClientName          string `json:"client_name,omitempty"`
	TargetURL           string `json:"target_url"`
	Username            string `json:"username,omitempty"`
	Password            string `json:"password,omitempty"`
	RecordedLoginScript string `json:"recorded_login_script,omitempty"`
	ScopeInclude        string `json:"scope_include,omitempty"`
	ScopeExclude        string `json:"scope_exclude,omitempty"`
	ProtocolOption      string `json:"protocol_option,omitempty"`
	ResourcePool        string `json:"resource_pool,omitempty"`
	CallbackURL         string `json:"callback_url,omitempty"`
	AdvancedScope       bool   `json:"advanced_scope,omitempty"`
}

// Load reads and validates a job spec from a JSON file.
func Load(path string) (*Spec, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read job file: %v", err)
	}

	var spec Spec
	if err := json.Unmarshal(data, &spec); err != nil {
		return nil, fmt.Errorf("failed to parse job file: %v", err)
	}

	if spec.TargetURL == "" {
		return nil, fmt.Errorf("job file missing required field: target_url")
	}

	return &spec, nil
}
