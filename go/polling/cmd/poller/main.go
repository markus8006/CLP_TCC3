package main

import (
    "bufio"
    "encoding/json"
    "fmt"
    "os"
    "sync"
    "time"
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
    _ = w.en.Encode(ev)
}

type poller struct {
    key      string
    interval time.Duration
    stop     chan struct{}
    done     chan struct{}
    w        *writer
}

func newPoller(key string, interval time.Duration, w *writer) *poller {
    if interval <= 0 {
        interval = time.Second
    }
    return &poller{
        key:      key,
        interval: interval,
        stop:     make(chan struct{}),
        done:     make(chan struct{}),
        w:        w,
    }
}

func (p *poller) run() {
    ticker := time.NewTicker(p.interval)
    defer func() {
        ticker.Stop()
        close(p.done)
    }()
    for {
        select {
        case <-ticker.C:
            p.w.send(event{Event: "poll", Key: p.key})
        case <-p.stop:
            return
        }
    }
}

func (p *poller) stopPoller() {
    select {
    case <-p.done:
        return
    default:
    }
    close(p.stop)
    <-p.done
}

type manager struct {
    mu      sync.Mutex
    pollers map[string]*poller
    w       *writer
}

func newManager(w *writer) *manager {
    return &manager{
        pollers: make(map[string]*poller),
        w:       w,
    }
}

func (m *manager) add(key string, interval time.Duration, eventName string) {
    if key == "" {
        m.w.send(event{Event: "error", Message: "empty key"})
        return
    }
    m.mu.Lock()
    defer m.mu.Unlock()
    if existing, ok := m.pollers[key]; ok {
        existing.stopPoller()
    }
    p := newPoller(key, interval, m.w)
    m.pollers[key] = p
    go p.run()
    m.w.send(event{Event: eventName, Key: key})
}

func (m *manager) remove(key string) {
    if key == "" {
        m.w.send(event{Event: "error", Message: "empty key"})
        return
    }
    m.mu.Lock()
    p, ok := m.pollers[key]
    if ok {
        delete(m.pollers, key)
    }
    m.mu.Unlock()

    if ok {
        p.stopPoller()
    }
    m.w.send(event{Event: "removed", Key: key})
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
        p.stopPoller()
    }
    m.w.send(event{Event: "shutdown"})
}

func parseInterval(raw int) time.Duration {
    if raw <= 0 {
        raw = 1000
    }
    return time.Duration(raw) * time.Millisecond
}

func main() {
    w := newWriter()
    mgr := newManager(w)
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
            mgr.add(cmd.Key, parseInterval(cmd.Interval), "added")
        case "update":
            mgr.add(cmd.Key, parseInterval(cmd.Interval), "updated")
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
