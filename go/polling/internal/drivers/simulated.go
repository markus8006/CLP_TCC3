package drivers

import (
	"fmt"
	"math"
	"sync"
	"time"
)

type simulatedDriver struct {
	protocol string
	config   SessionConfig
	mu       sync.Mutex
	state    map[string]float64
}

func newSimulatedDriver(protocol string, cfg SessionConfig) *simulatedDriver {
	return &simulatedDriver{
		protocol: protocol,
		config:   cfg,
		state:    make(map[string]float64),
	}
}

func (d *simulatedDriver) Connect() error    { return nil }
func (d *simulatedDriver) Disconnect() error { return nil }

func (d *simulatedDriver) ReadTags(tags []TagConfig) (map[string]interface{}, error) {
	d.mu.Lock()
	defer d.mu.Unlock()

	out := make(map[string]interface{}, len(tags))
	base := float64(time.Now().UnixNano()%1_000_000) / 1_000.0
	for idx, tag := range tags {
		key := tag.Address
		seq := d.state[key]
		seq += 1 + float64(idx)
		d.state[key] = seq

		value := base + seq
		switch tag.DataType {
		case "BOOL", "bool":
			value = math.Mod(seq, 2)
			out[tag.Name] = value > 0.5
		case "INT", "DINT", "int", "int32", "INT16", "INT32":
			out[tag.Name] = int(value)
		default:
			out[tag.Name] = math.Round(value*100) / 100
		}
	}
	return out, nil
}

func NewDriverForProtocol(protocol string, cfg SessionConfig) (PollingDriver, error) {
	switch protocol {
	case "modbus":
		return newSimulatedDriver("modbus", cfg), nil
	case "s7":
		return newSimulatedDriver("s7", cfg), nil
	case "opcua":
		return newSimulatedDriver("opcua", cfg), nil
	case "ethernetip", "cip":
		return newSimulatedDriver("ethernetip", cfg), nil
	case "beckhoff", "ads":
		return newSimulatedDriver("beckhoff", cfg), nil
	default:
		return nil, fmt.Errorf("driver não suportado: %s", protocol)
	}
}
