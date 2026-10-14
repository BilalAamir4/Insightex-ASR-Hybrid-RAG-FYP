# M6 manual browser check report

Date: 2026-10-14 to 2026-10-15. Browser: the user's own Chrome. Checklist: `manual_checklist.md`.

## Result: pass (with the limits below)

- Server start and the Day 4 upload were done by an agent through the API, because its browser could not run (Playwright download returned 404). The checks in the browser were done by the user.
- Part A, B: pass.
- Part C: buttons and jumps checked in the browser. **The audio at the jumped-to moments was not listened to**, so "heard it" is not confirmed.
- Part D: fallback (`llm_not_loaded`) and automatic re-warm pass (log lines below). Empty and over-length limits pass. **The old-lecture disabled-box check was not tried.**
- Part E: question words found in the log: 0. 13 ask-log lines (11 asks, 2 warm-ups).

## Log lines (as pasted by the user)

```
2026-10-14 23:52:49,897 INFO insightex.ask: {"event": "warm_up", "result": "loaded", "reason": null, "ms": 20592.0}
2026-10-14 23:53:03,777 INFO insightex.ask: {"event": "ask", "total_ms": 700.7, "rewrite_ms": 515.2, "search_ms": 141.4, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:56:11,574 INFO insightex.ask: {"event": "ask", "total_ms": 617.0, "rewrite_ms": 379.1, "search_ms": 210.5, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:56:56,745 INFO insightex.ask: {"event": "ask", "total_ms": 847.0, "rewrite_ms": 477.5, "search_ms": 354.6, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:58:19,382 INFO insightex.ask: {"event": "ask", "total_ms": 795.3, "rewrite_ms": 497.3, "search_ms": 282.9, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:58:32,214 INFO insightex.ask: {"event": "ask", "total_ms": 864.7, "rewrite_ms": 564.2, "search_ms": 285.5, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:58:56,144 INFO insightex.ask: {"event": "ask", "total_ms": 894.8, "rewrite_ms": 650.2, "search_ms": 228.9, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-14 23:59:06,773 INFO insightex.ask: {"event": "ask", "total_ms": 1020.9, "rewrite_ms": 650.7, "search_ms": 355.7, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-15 00:01:17,451 INFO insightex.ask: {"event": "ask", "total_ms": 78.3, "rewrite_ms": null, "search_ms": 62.7, "rewrite_used": false, "fallback_reason": "llm_not_loaded", "citations": 3}
2026-10-15 00:01:23,583 INFO insightex.ask: {"event": "warm_up", "result": "loaded", "reason": null, "ms": 5949.5}
2026-10-15 00:03:59,991 INFO insightex.ask: {"event": "ask", "total_ms": 627.7, "rewrite_ms": 506.7, "search_ms": 100.8, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-15 00:05:26,956 INFO insightex.ask: {"event": "ask", "total_ms": 638.6, "rewrite_ms": 446.7, "search_ms": 169.0, "rewrite_used": true, "fallback_reason": null, "citations": 3}
2026-10-15 00:13:58,716 INFO insightex.ask: {"event": "ask", "total_ms": 734.2, "rewrite_ms": 604.4, "search_ms": 114.4, "rewrite_used": true, "fallback_reason": null, "citations": 3}
```

## Open items carried forward

- Audio at the cited moments not listened to (Part C).
- Old-lecture (non-indexed) disabled ask box not checked in a browser (Part D).
- Day 4 link-path checks (duration 688 ±1 s, first 20 segments) not done: no URL was supplied.
