package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	pb "clp/polling/polling"
	"github.com/joho/godotenv"
	"google.golang.org/grpc"
)

type pollingServer struct {
	pb.UnimplementedPollingServiceServer
}

type pollingConfig struct {
	PLCs []plcDescriptor `json:"plcs"`
}

type plcDescriptor struct {
	ID              int                  `json:"id"`
	Name            string               `json:"name"`
	IPAddress       string               `json:"ip_address"`
	VlanID          *int                 `json:"vlan_id"`
	Protocol        string               `json:"protocol"`
	PollingInterval int                  `json:"polling_interval"`
	Registers       []registerDescriptor `json:"registers"`
}

type registerDescriptor struct {
	ID       int    `json:"id"`
	Name     string `json:"name"`
	Address  string `json:"address"`
	PollRate int    `json:"poll_rate"`
	Unit     string `json:"unit"`
}

type measurementPayload struct {
	PLCID      int       `json:"plc_id"`
	RegisterID int       `json:"register_id"`
	Status     string    `json:"status"`
	Value      *float64  `json:"value,omitempty"`
	ValueFloat *float64  `json:"value_float,omitempty"`
	RawValue   any       `json:"raw_value,omitempty"`
	Quality    string    `json:"quality,omitempty"`
	Unit       string    `json:"unit,omitempty"`
	Timestamp  time.Time `json:"timestamp"`
	Error      string    `json:"error,omitempty"`
}

var (
	configMu      sync.RWMutex
	currentConfig pollingConfig
)

func main() {
	if err := loadDotEnv(); err != nil {
		log.Printf("warning: failed to load .env file: %v", err)
	}

	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to bind gRPC listener: %v", err)
	}

	server := grpc.NewServer()
	pb.RegisterPollingServiceServer(server, &pollingServer{})

	go func() {
		log.Printf("gRPC polling server listening on %s", lis.Addr())
		if err := server.Serve(lis); err != nil {
			log.Fatalf("gRPC server error: %v", err)
		}
	}()

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	<-sigs
	log.Print("shutdown signal received, stopping gRPC server")
	server.GracefulStop()
}

func (s *pollingServer) UpdateConfig(ctx context.Context, req *pb.ConfigPayload) (*pb.StatusResponse, error) {
	var cfg pollingConfig
	if err := json.Unmarshal([]byte(req.GetJsonConfig()), &cfg); err != nil {
		log.Printf("failed to decode configuration: %v", err)
		return &pb.StatusResponse{Success: false, Message: fmt.Sprintf("invalid config: %v", err)}, nil
	}

	configMu.Lock()
	currentConfig = cfg
	configMu.Unlock()

	log.Printf("configuration updated: %d PLCs registered", len(cfg.PLCs))
	return &pb.StatusResponse{Success: true, Message: "configuration updated"}, nil
}

func (s *pollingServer) StreamData(req *pb.Empty, stream pb.PollingService_StreamDataServer) error {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case <-ticker.C:
			configMu.RLock()
			cfg := currentConfig
			configMu.RUnlock()

			measurements := pollAllPLCs(stream.Context(), cfg)
			for _, measurement := range measurements {
				data, err := json.Marshal(measurement)
				if err != nil {
					log.Printf("failed to marshal measurement: %v", err)
					continue
				}
				if err := stream.Send(&pb.DataPayload{JsonData: string(data)}); err != nil {
					return err
				}
			}
		}
	}
}

func pollAllPLCs(ctx context.Context, cfg pollingConfig) []measurementPayload {
	results := make([]measurementPayload, 0)
	for _, plc := range cfg.PLCs {
		if len(plc.Registers) == 0 {
			continue
		}
		for _, reg := range plc.Registers {
			select {
			case <-ctx.Done():
				return results
			default:
			}

			measurementTime := time.Now().UTC()
			value, err := readRegister(plc, reg)
			payload := measurementPayload{
				PLCID:      plc.ID,
				RegisterID: reg.ID,
				Timestamp:  measurementTime,
			}

			if err != nil {
				payload.Status = "offline"
				payload.Error = err.Error()
				log.Printf("failed to poll PLC %s (%d) register %s (%d): %v", plc.Name, plc.ID, reg.Name, reg.ID, err)
			} else {
				payload.Status = "online"
				payload.Quality = "GOOD"
				if reg.Unit != "" {
					payload.Unit = reg.Unit
				}
				payload.Value = &value
				payload.ValueFloat = &value
				payload.RawValue = value
			}

			results = append(results, payload)
		}
	}
	return results
}

func readRegister(plc plcDescriptor, reg registerDescriptor) (float64, error) {
	_ = plc
	_ = reg
	simulated := float64(time.Now().UnixNano()%100_000) / 1000.0
	return simulated, nil
}

func loadDotEnv() error {
	wd, err := os.Getwd()
	if err != nil {
		return err
	}

	for {
		envPath := filepath.Join(wd, ".env")
		if _, err := os.Stat(envPath); err == nil {
			return godotenv.Overload(envPath)
		}

		parent := filepath.Dir(wd)
		if parent == wd {
			break
		}
		wd = parent
	}

	return fmt.Errorf(".env file not found")
}
