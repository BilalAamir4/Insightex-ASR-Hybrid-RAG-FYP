#!/bin/bash
ps aux | grep -E "python|load_single" | grep -v grep
