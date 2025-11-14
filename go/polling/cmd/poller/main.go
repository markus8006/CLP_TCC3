package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/joho/godotenv"
)

type command struct {
	Cmd      string `json:"cmd"`
	Key      string `json:"key,omitempty"`
	Interval int    `json:"interval,omitempty"`
}

type event struct {
	Event   string `json:"event"`
	Key     string `json:"key,omitempty"`
	Message string `json:"message,omitempty"`
}

type writer struct {
	mu sync.Mutex
	en *json.Encoder
}

func newWriter() *writer {
	return &writer{en: json.NewEncoder(os.Stdout)}
}

func (w *writer) send(ev event) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if err := w.en.Encode(ev); err != nil {
		log.Printf("falha ao enviar evento %s: %v", ev.Event, err)
	}
}

type serviceConfig struct {
	backendURL string
	apiKey     string
	httpClient *http.Client
}

type backendClient struct {
	cfg serviceConfig
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
	Quality    string    `json:"quality,omitempty"`
	Unit       string    `json:"unit,omitempty"`
	Timestamp  time.Time `json:"timestamp"`
	Error      string    `json:"error,omitempty"`
}

type pollerUpdate struct {
	interval time.Duration
	meta     plcDescriptor
}

type poller struct {
	ctx      context.Context
	key      string
	backend  *backendClient
	writer   *writer
	mu       sync.RWMutex
	interval time.Duration
	meta     plcDescriptor
	updates  chan pollerUpdate
	stopCh   chan struct{}
	done     chan struct{}
}

type manager struct {
	ctx     context.Context
	backend *backendClient
	writer  *writer
	mu      sync.Mutex
	pollers map[string]*poller
}

func main() {


	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := loadDotEnv(); err != nil {
		log.Printf("warning: failed to load .env file: %v", err)
	}

	cfg := loadConfig()
	client := &backendClient{cfg: cfg}
	w := newWriter()
	mgr := newManager(ctx, client, w)

	w.send(event{Event: "ready"})

	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		line := scanner.Bytes()
		var cmd command
		if err := json.Unmarshal(line, &cmd); err != nil {
			w.send(event{Event: "error", Message: fmt.Sprintf("invalid command: %v", err)})
			continue
		}
		switch cmd.Cmd {
		case "add":
			mgr.add(cmd.Key, parseInterval(cmd.Interval))
		case "update":
			mgr.update(cmd.Key, parseInterval(cmd.Interval))
		case "remove":
			mgr.remove(cmd.Key)
		case "shutdown":
			mgr.shutdown()
			return
		default:
			w.send(event{Event: "error", Message: fmt.Sprintf("unknown command: %s", cmd.Cmd)})
		}
	}

	if err := scanner.Err(); err != nil {
		w.send(event{Event: "error", Message: fmt.Sprintf("scanner error: %v", err)})
	}
	mgr.shutdown()
}

func loadConfig() serviceConfig {
	baseURL := strings.TrimSuffix(os.Getenv("BACKEND_API_URL"), "/")
	if baseURL == "" {
		baseURL = "http://localhost:5000"
	}

	apiKey := strings.TrimSpace(os.Getenv("POLLER_API_KEY"))
	fmt.Println("API key lida:", os.Getenv("POLLER_API_KEY"))
	if apiKey == "" {
		log.Printf("warning: POLLER_API_KEY não configurada; requests de ingestão serão rejeitados")
	}

	return serviceConfig{
		backendURL: baseURL,
		apiKey:     apiKey,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
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

func newManager(ctx context.Context, backend *backendClient, w *writer) *manager {
	return &manager{
		ctx:     ctx,
		backend: backend,
		writer:  w,
		pollers: make(map[string]*poller),
	}
}

func (m *manager) add(key string, interval time.Duration) {
	if key == "" {
		m.writer.send(event{Event: "error", Message: "empty key"})
		return
	}

	meta, err := m.backend.fetchPLCByKey(m.ctx, key)
	if err != nil {
		log.Printf("falha ao carregar metadados do PLC %s: %v", key, err)
		meta = plcDescriptor{}
	}

	if interval <= 0 {
		if meta.PollingInterval > 0 {
			interval = time.Duration(meta.PollingInterval) * time.Millisecond
		} else {
			interval = time.Second
		}
	}

	p := newPoller(m.ctx, key, interval, meta, m.backend, m.writer)

	m.mu.Lock()
	if existing, ok := m.pollers[key]; ok {
		existing.stop()
	}
	m.pollers[key] = p
	m.mu.Unlock()

	go p.run()
	m.writer.send(event{Event: "added", Key: key})
}

func (m *manager) update(key string, interval time.Duration) {
	if key == "" {
		m.writer.send(event{Event: "error", Message: "empty key"})
		return
	}

	meta, err := m.backend.fetchPLCByKey(m.ctx, key)
	if err != nil {
		m.writer.send(event{Event: "error", Key: key, Message: err.Error()})
		return
	}

	if interval <= 0 {
		if meta.PollingInterval > 0 {
			interval = time.Duration(meta.PollingInterval) * time.Millisecond
		} else {
			interval = time.Second
		}
	}

	m.mu.Lock()
	if existing, ok := m.pollers[key]; ok {
		existing.update(interval, meta)
		m.mu.Unlock()
		m.writer.send(event{Event: "updated", Key: key})
		return
	}
	m.mu.Unlock()

	m.add(key, interval)
}

func (m *manager) remove(key string) {
	if key == "" {
		m.writer.send(event{Event: "error", Message: "empty key"})
		return
	}

	m.mu.Lock()
	p, ok := m.pollers[key]
	if ok {
		delete(m.pollers, key)
	}
	m.mu.Unlock()

	if ok {
		p.stop()
	}
	m.writer.send(event{Event: "removed", Key: key})
}

func (m *manager) shutdown() {
	m.mu.Lock()
	pollers := make([]*poller, 0, len(m.pollers))
	for _, p := range m.pollers {
		pollers = append(pollers, p)
	}
	m.pollers = make(map[string]*poller)
	m.mu.Unlock()

	for _, p := range pollers {
		p.stop()
	}
	m.writer.send(event{Event: "shutdown"})
}

func newPoller(ctx context.Context, key string, interval time.Duration, meta plcDescriptor, backend *backendClient, w *writer) *poller {
	if interval <= 0 {
		interval = time.Second
	}
	return &poller{
		ctx:      ctx,
		key:      key,
		backend:  backend,
		writer:   w,
		interval: interval,
		meta:     meta,
		updates:  make(chan pollerUpdate, 1),
		stopCh:   make(chan struct{}),
		done:     make(chan struct{}),
	}
}

func (p *poller) run() {
	defer close(p.done)

	ticker := time.NewTicker(p.snapshotInterval())
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			p.pollOnce()
		case update := <-p.updates:
			p.applyUpdate(update)
			ticker.Reset(p.snapshotInterval())
		case <-p.stopCh:
			return
		case <-p.ctx.Done():
			return
		}
	}
}

func (p *poller) stop() {
	select {
	case <-p.done:
		return
	default:
	}
	close(p.stopCh)
	<-p.done
}

func (p *poller) update(interval time.Duration, meta plcDescriptor) {
	p.updates <- pollerUpdate{interval: interval, meta: meta}
}

func (p *poller) applyUpdate(update pollerUpdate) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if update.interval > 0 {
		p.interval = update.interval
	}
	if update.meta.ID != 0 {
		p.meta = update.meta
	}
}

func (p *poller) snapshotInterval() time.Duration {
	p.mu.RLock()
	defer p.mu.RUnlock()
	if p.interval <= 0 {
		return time.Second
	}
	return p.interval
}

func (p *poller) snapshotMeta() plcDescriptor {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.meta
}

func (p *poller) pollOnce() {
	if p.writer != nil {
		p.writer.send(event{Event: "poll", Key: p.key})
	}

	meta := p.snapshotMeta()
	if meta.ID == 0 || len(meta.Registers) == 0 {
		return
	}

	for _, reg := range meta.Registers {
		measurementTime := time.Now().UTC()
		value, err := readRegister(meta, reg)
		payload := measurementPayload{
			PLCID:      meta.ID,
			RegisterID: reg.ID,
			Timestamp:  measurementTime,
		}

		if err != nil {
			payload.Status = "offline"
			payload.Error = err.Error()
		} else {
			payload.Status = "online"
			payload.Quality = "GOOD"
			if reg.Unit != "" {
				payload.Unit = reg.Unit
			}
			payload.Value = &value
			payload.ValueFloat = &value
		}

		ctx, cancel := context.WithTimeout(p.ctx, 5*time.Second)
		p.backend.sendMeasurement(ctx, payload)
		cancel()
	}
}

func readRegister(plc plcDescriptor, reg registerDescriptor) (float64, error) {
	_ = plc
	_ = reg
	simulated := float64(time.Now().UnixNano()%100_000) / 1000.0
	return simulated, nil
}

func (c *backendClient) fetchPLCByKey(ctx context.Context, key string) (plcDescriptor, error) {
	ip, vlan, err := splitKey(key)
	if err != nil {
		return plcDescriptor{}, err
	}

	url := c.cfg.backendURL + "/api/v1/plcs"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return plcDescriptor{}, err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.cfg.httpClient.Do(req)
	if err != nil {
		return plcDescriptor{}, fmt.Errorf("falha ao requisitar lista de PLCs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= http.StatusBadRequest {
		body, _ := io.ReadAll(resp.Body)
		return plcDescriptor{}, fmt.Errorf("backend respondeu %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return plcDescriptor{}, err
	}

	var list []plcDescriptor
	if err := json.Unmarshal(raw, &list); err != nil {
		var wrapper struct {
			Items []plcDescriptor `json:"items"`
			Data  []plcDescriptor `json:"data"`
		}
		if err := json.Unmarshal(raw, &wrapper); err != nil {
			return plcDescriptor{}, fmt.Errorf("resposta inesperada do backend: %w", err)
		}
		if len(wrapper.Items) > 0 {
			list = wrapper.Items
		} else {
			list = wrapper.Data
		}
	}

	for _, plc := range list {
		if !strings.EqualFold(plc.IPAddress, ip) {
			continue
		}
		if vlan == nil {
			if plc.VlanID == nil || *plc.VlanID == 0 {
				return plc, nil
			}
			continue
		}
		if plc.VlanID != nil && *plc.VlanID == *vlan {
			return plc, nil
		}
	}

	return plcDescriptor{}, fmt.Errorf("plc %s não encontrado", key)
}

func (c *backendClient) sendMeasurement(ctx context.Context, payload measurementPayload) {
	body := new(bytes.Buffer)
	if err := json.NewEncoder(body).Encode(payload); err != nil {
		log.Printf("falha ao serializar payload: %v", err)
		return
	}

	url := c.cfg.backendURL + "/api/v1/internal/poller-data"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, body)
	if err != nil {
		log.Printf("falha ao construir request de ingestão: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if c.cfg.apiKey != "" {
		req.Header.Set("X-API-KEY", c.cfg.apiKey)
	}

	resp, err := c.cfg.httpClient.Do(req)
	if err != nil {
		log.Printf("falha ao enviar dados do PLC %d: %v", payload.PLCID, err)
		return
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	if resp.StatusCode >= http.StatusBadRequest {
		log.Printf(
			"backend respondeu %d para plc=%d register=%d",
			resp.StatusCode,
			payload.PLCID,
			payload.RegisterID,
		)
	}
}

func parseInterval(raw int) time.Duration {
	if raw <= 0 {
		return 0
	}
	return time.Duration(raw) * time.Millisecond
}

func splitKey(key string) (string, *int, error) {
	parts := strings.SplitN(key, "|", 2)
	if len(parts) == 0 {
		return "", nil, fmt.Errorf("chave inválida: %s", key)
	}
	ip := parts[0]
	if len(parts) == 1 {
		return ip, nil, nil
	}
	vlanRaw := strings.TrimSpace(parts[1])
	if vlanRaw == "" {
		return ip, nil, nil
	}
	vlanInt, err := strconv.Atoi(vlanRaw)
	if err != nil {
		return "", nil, fmt.Errorf("vlan inválida na chave %s", key)
	}
	if vlanInt == 0 {
		return ip, nil, nil
	}
	return ip, &vlanInt, nil
}
