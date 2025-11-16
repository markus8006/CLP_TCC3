package drivers

// TagConfig descreve um ponto de coleta individual.
type TagConfig struct {
	ID       int                    `json:"id"`
	Name     string                 `json:"name"`
	Address  string                 `json:"address"`
	DataType string                 `json:"data_type"`
	Meta     map[string]interface{} `json:"metadata,omitempty"`
}

// SessionConfig agrupa todas as tags relacionadas a um CLP/protocolo específico.
type SessionConfig struct {
	ID         int                    `json:"id"`
	PLCID      int                    `json:"plc_id"`
	Name       string                 `json:"name"`
	Protocol   string                 `json:"protocol"`
	IntervalMs int                    `json:"interval_ms"`
	Connection map[string]interface{} `json:"connection"`
	Tags       []TagConfig            `json:"tags"`
}

// PollingDriver é a interface mínima exigida para os drivers escritos em Go.
type PollingDriver interface {
	Connect() error
	Disconnect() error
	ReadTags([]TagConfig) (map[string]interface{}, error)
}
