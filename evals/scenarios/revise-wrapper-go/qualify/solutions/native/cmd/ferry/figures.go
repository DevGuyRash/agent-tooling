package main

import (
	"slices"
	"sort"

	"inchmara.example/ferry/internal/sailings"
)

const (
	onTimeLimit = 5 // a sailing at most this many minutes late is on time; early ones are too
	bandWidth   = 5 // minutes per band of the delay histogram
)

// figures computes each route's punctuality figures (docs/punctuality.md), least punctual route first.
func figures(ss []sailings.Sailing) []routeFigures {
	var order []string
	delays := map[string][]int{}
	cancelled := map[string]int{}
	for _, s := range ss {
		if _, seen := delays[s.Route]; !seen {
			order = append(order, s.Route)
			delays[s.Route] = []int{}
		}
		if s.Cancelled {
			cancelled[s.Route]++
			continue
		}
		delays[s.Route] = append(delays[s.Route], s.Delay)
	}
	routes := make([]routeFigures, 0, len(order))
	for _, route := range order {
		ran := delays[route]
		f := routeFigures{Route: route, Sailings: len(ran) + cancelled[route], Cancelled: cancelled[route]}
		counts := map[int]int{}
		for _, d := range ran {
			if d <= onTimeLimit {
				f.OnTime++
			}
			counts[floorDiv(d, bandWidth)*bandWidth]++
		}
		for start, n := range counts {
			f.Bands = append(f.Bands, [2]int{start, n})
		}
		sort.Slice(f.Bands, func(i, j int) bool { return f.Bands[i][0] < f.Bands[j][0] })
		if len(ran) > 0 {
			sorted := slices.Clone(ran)
			slices.Sort(sorted)
			mid := len(sorted) / 2
			median := float64(sorted[mid])
			if len(sorted)%2 == 0 {
				median = float64(sorted[mid-1]+sorted[mid]) / 2
			}
			worst := sorted[len(sorted)-1]
			f.Median, f.Worst = &median, &worst
		}
		routes = append(routes, f)
	}
	// Least punctual first; equal shares keep the order the routes first appeared in.
	sort.SliceStable(routes, func(i, j int) bool { return share(routes[i]) < share(routes[j]) })
	return routes
}

// share is the part of a route's sailings that ran which were on time; -1 when nothing ran, so it comes first.
func share(f routeFigures) float64 {
	ran := f.Sailings - f.Cancelled
	if ran == 0 {
		return -1
	}
	return float64(f.OnTime) / float64(ran)
}

// floorDiv divides rounding down, so 1 to 5 minutes early is band -5, not band 0.
func floorDiv(a, b int) int {
	q := a / b
	if a%b != 0 && (a < 0) != (b < 0) {
		q--
	}
	return q
}
