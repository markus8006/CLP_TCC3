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

	"clp/polling/internal/drivers"
	pb "clp/polling/polling"
	"github.com/joho/godotenv"
	"google.golang.org/grpc"
)

type pollingServer struct {
	pb.UnimplementedPollingServiceServer
	mu       sync.RWMutex
	sessions []sessionRuntime
}

type sessionRuntime struct {
	config drivers.SessionConfig
	driver drivers.PollingDriver
}

type pollingConfig struct {
	Sessions []drivers.SessionConfig `json:"sessions"`
}

func main() {
	if err := loadDotEnv(); err != nil {
		log.Printf("warning: failed to load .env file: %v", err)
	}

	lis, err := net.Listen("tcp", ":50051")
	if err != nil {
		log.Fatalf("failed to bind gRPC listener: %v", err)
	}

	server := grpc.NewServer()
	pollingSrv := &pollingServer{}
	pb.RegisterPollingServiceServer(server, pollingSrv)

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
	pollingSrv.shutdown()
}

func (s *pollingServer) UpdateConfig(ctx context.Context, req *pb.ConfigPayload) (*pb.StatusResponse, error) {
	var cfg pollingConfig
	if err := json.Unmarshal([]byte(req.GetJsonConfig()), &cfg); err != nil {
		log.Printf("failed to decode configuration: %v", err)
		return &pb.StatusResponse{Success: false, Message: fmt.Sprintf("invalid config: %v", err)}, nil
	}

	runtimes := make([]sessionRuntime, 0, len(cfg.Sessions))
	for _, session := range cfg.Sessions {
		driver, err := drivers.NewDriverForProtocol(session.Protocol, session)
		if err != nil {
			return &pb.StatusResponse{Success: false, Message: err.Error()}, nil
		}
		if err := driver.Connect(); err != nil {
			return &pb.StatusResponse{Success: false, Message: err.Error()}, nil
		}
		runtimes = append(runtimes, sessionRuntime{config: session, driver: driver})
	}

	s.mu.Lock()
	old := s.sessions
	s.sessions = runtimes
	s.mu.Unlock()

	for _, runtime := range old {
		_ = runtime.driver.Disconnect()
	}

	log.Printf("configuration updated: %d sessions active", len(runtimes))
	return &pb.StatusResponse{Success: true, Message: "configuration updated"}, nil
}

func (s *pollingServer) StreamData(req *pb.Empty, stream pb.PollingService_StreamDataServer) error {
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-stream.Context().Done():
			return stream.Context().Err()
		case <-ticker.C:
			payloads := s.collectMeasurements()
			for _, measurement := range payloads {
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

func (s *pollingServer) collectMeasurements() []measurementPayload {
	sessions := s.snapshotSessions()
	var output []measurementPayload
	for _, runtime := range sessions {
		output = append(output, pollSession(runtime)...)
	}
	return output
}

func (s *pollingServer) snapshotSessions() []sessionRuntime {
	s.mu.RLock()
	defer s.mu.RUnlock()
	cloned := make([]sessionRuntime, len(s.sessions))
	copy(cloned, s.sessions)
	return cloned
}

func (s *pollingServer) shutdown() {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, runtime := range s.sessions {
		_ = runtime.driver.Disconnect()
	}
	s.sessions = nil
}

type measurementPayload struct {
	PLCID      int         `json:"plc_id"`
	RegisterID int         `json:"register_id"`
	Protocol   string      `json:"protocol"`
	Status     string      `json:"status"`
	Quality    string      `json:"quality"`
	Timestamp  time.Time   `json:"timestamp"`
	Tag        string      `json:"tag"`
	Address    string      `json:"address"`
	RawValue   interface{} `json:"raw_value,omitempty"`
	ValueFloat *float64    `json:"value_float,omitempty"`
	ValueInt   *int        `json:"value_int,omitempty"`
	Error      string      `json:"error,omitempty"`
}

func pollSession(runtime sessionRuntime) []measurementPayload {
	values, err := runtime.driver.ReadTags(runtime.config.Tags)
	timestamp := time.Now().UTC()

	results := make([]measurementPayload, 0, len(runtime.config.Tags))
	if err != nil {
		for _, tag := range runtime.config.Tags {
			results = append(results, measurementPayload{
				PLCID:      runtime.config.PLCID,
				RegisterID: tag.ID,
				Protocol:   runtime.config.Protocol,
				Status:     "error",
				Quality:    "BAD",
				Timestamp:  timestamp,
				Tag:        tag.Name,
				Address:    tag.Address,
				Error:      err.Error(),
			})
		}
		return results
	}

	for _, tag := range runtime.config.Tags {
		value, ok := values[tag.Name]
		payload := measurementPayload{
			PLCID:      runtime.config.PLCID,
			RegisterID: tag.ID,
			Protocol:   runtime.config.Protocol,
			Status:     "online",
			Quality:    "GOOD",
			Timestamp:  timestamp,
			Tag:        tag.Name,
			Address:    tag.Address,
		}
		if ok {
			payload.RawValue = value
			switch typed := value.(type) {
			case float64:
				payload.ValueFloat = floatPtr(typed)
			case int:
				payload.ValueInt = intPtr(typed)
				payload.ValueFloat = floatPtr(float64(typed))
			case int32:
				payload.ValueInt = intPtr(int(typed))
				payload.ValueFloat = floatPtr(float64(typed))
			case bool:
				if typed {
					payload.ValueInt = intPtr(1)
					payload.ValueFloat = floatPtr(1)
				} else {
					payload.ValueInt = intPtr(0)
					payload.ValueFloat = floatPtr(0)
				}
			}
		} else {
			payload.Status = "offline"
			payload.Quality = "BAD"
		}
		results = append(results, payload)
	}
	return results
}

func floatPtr(value float64) *float64 {
	v := value
	return &v
}

func intPtr(value int) *int {
	v := value
	return &v
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
	return fmt.Errorf(".env not found")
}
