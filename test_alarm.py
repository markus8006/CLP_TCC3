#!/usr/bin/env python3
"""
perf_passive.py

Uso:
  python tests/perf_passive.py --ips 127.0.0.1 127.0.0.2 --samples 200 --interval 0.5

Descrição:
- Faz N requisições à API /api/get/data/clp/<ip> para cada IP listado.
- Mede latência HTTP e extrai timestamps/valores retornados.
- Gera métricas por PLC e por register.
"""
import argparse
import time
import requests
import statistics
from collections import defaultdict
from datetime import datetime

API_FMT = "http://localhost:5000/api/get/data/clp/{}"  # ajuste se necessário

def now_s():
    return time.time()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--ips', nargs='+', required=True, help='Lista de IPs dos PLCs')
    p.add_argument('--samples', type=int, default=200, help='Número de polls por PLC')
    p.add_argument('--interval', type=float, default=0.5, help='Intervalo entre polls (segundos)')
    p.add_argument('--timeout', type=float, default=5.0, help='Timeout HTTP (s)')
    return p.parse_args()

def extract_latest_per_register(payload):
    """
    payload: json retornado da API (com campos `registers` e `data`)
    retorna dict { register_id_str: {value: float, timestamp: iso, unit: str}}
    """
    out = {}
    data = payload.get('data', []) or []
    # considera apenas último timestamp por register
    latest = {}
    for p in data:
        rid = str(p.get('register_id'))
        ts = p.get('timestamp') or p.get('created_at') or None
        try:
            tval = datetime.fromisoformat(ts) if ts else None
        except Exception:
            tval = None
        # pega valor (float preferencial)
        try:
            val = float(p.get('value_float')) if p.get('value_float') is not None else (float(p.get('value_int')) if p.get('value_int') is not None else float(p.get('raw_value') or float('nan')))
        except Exception:
            val = float('nan')
        if rid not in latest or (tval and latest[rid]['tval'] and tval > latest[rid]['tval']) or (tval and not latest[rid]['tval']):
            latest[rid] = {'value': val, 'ts': ts, 'tval': tval, 'unit': p.get('unit')}
    for rid, v in latest.items():
        out[rid] = {'value': v['value'], 'timestamp': v['ts'], 'unit': v['unit']}
    return out

def run_passive(ips, samples, interval, timeout):
    results = {}
    for ip in ips:
        print(f"\n== PLC {ip} — começando {samples} polls a cada {interval}s ==")
        latencies = []
        per_register_samples = defaultdict(list)  # rid -> list of (ts_str, value, recv_time)
        missing_count = 0
        for i in range(samples):
            t0 = now_s()
            try:
                r = requests.get(API_FMT.format(ip), timeout=timeout)
                latency = now_s() - t0
                if r.status_code != 200:
                    print(f"[{ip}] req {i} -> status {r.status_code}")
                    missing_count += 1
                else:
                    latencies.append(latency)
                    payload = r.json()
                    latest = extract_latest_per_register(payload)
                    recv_time = datetime.utcnow().isoformat()
                    for rid, info in latest.items():
                        per_register_samples[rid].append((info.get('timestamp'), info.get('value'), recv_time))
            except Exception as e:
                latency = now_s() - t0
                print(f"[{ip}] Erro na requisição #{i}: {e}")
                missing_count += 1
            time.sleep(interval)

        # métricas
        def stats(lst):
            if not lst: return {}
            return {
                'count': len(lst),
                'min': min(lst),
                'max': max(lst),
                'mean': statistics.mean(lst),
                'median': statistics.median(lst),
                'p95': sorted(lst)[int(len(lst)*0.95)-1] if len(lst)>=1 else sorted(lst)[-1],
                'stdev': statistics.stdev(lst) if len(lst) >= 2 else 0.0
            }

        lat_stats = stats(latencies)
        print(f"\n>> Latência HTTP (s): {lat_stats}")
        print(f"Requests perdidos/erro: {missing_count} de {samples}")

        # métricas por register
        for rid, samples_list in per_register_samples.items():
            vals = [v for (_, v, _) in samples_list if v == v]  # remove NaN
            times = [datetime.fromisoformat(ts) for (ts, _, _) in samples_list if ts]
            inter_arrival = []
            if len(times) >= 2:
                times_epoch = [t.timestamp() for t in times]
                for a,b in zip(times_epoch, times_epoch[1:]):
                    inter_arrival.append(b - a)
            print(f"\n Register {rid}: amostras={len(samples_list)} valores_validos={len(vals)}")
            if vals:
                print(f"   valor último={vals[-1]} unidade={(samples_list[-1][0])}")
                print(f"   stats valor -> mean={statistics.mean(vals):.4f} stdev={statistics.stdev(vals) if len(vals)>1 else 0.0:.4f}")
            if inter_arrival:
                print(f"   inter-arrival (s): mean={statistics.mean(inter_arrival):.4f} stdev={statistics.stdev(inter_arrival) if len(inter_arrival)>1 else 0.0:.4f}")
        results[ip] = {'latencies': latencies, 'registers': per_register_samples}
    return results

if __name__ == '__main__':
    args = parse_args()
    run_passive(args.ips, args.samples, args.interval, args.timeout)
