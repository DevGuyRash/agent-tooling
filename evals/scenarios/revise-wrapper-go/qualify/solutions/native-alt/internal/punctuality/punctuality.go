// Package punctuality computes the per-route punctuality figures of docs/punctuality.md, as
// scripts/punctuality.py does.
package punctuality

import (
	"math"
	"slices"
	"sort"
)

// Sailing is what the figures need of a sailing: its route, and its delay in minutes unless it was cancelled.
type Sailing struct {
	Route     string
	Delay     int
	Cancelled bool
}

// Route is one route's figures.
type Route struct {
	Name      string
	Sailings  int
	Cancelled int
	OnTime    int
	Median    float64 // meaningful only when Ran() > 0
	Worst     int     // likewise
	Bands     []Band
}

// Band counts the sailings whose delay falls in [Start, Start+5).
type Band struct{ Start, Count int }

// Ran is the number of the route's sailings that were not cancelled.
func (r Route) Ran() int { return r.Sailings - r.Cancelled }

// Figures returns each route's figures, least punctual first; routes with equal shares keep the order in
// which they first appear.
func Figures(ss []Sailing) []Route {
	index := map[string]int{}
	var routes []Route
	var delays [][]int
	for _, s := range ss {
		i, ok := index[s.Route]
		if !ok {
			i = len(routes)
			index[s.Route] = i
			routes = append(routes, Route{Name: s.Route})
			delays = append(delays, nil)
		}
		routes[i].Sailings++
		if s.Cancelled {
			routes[i].Cancelled++
		} else {
			delays[i] = append(delays[i], s.Delay)
		}
	}
	for i := range routes {
		fill(&routes[i], delays[i])
	}
	keys := make([]float64, len(routes))
	for i, r := range routes {
		keys[i] = -1
		if r.Ran() > 0 {
			keys[i] = float64(r.OnTime) / float64(r.Ran())
		}
	}
	idx := make([]int, len(routes))
	for i := range idx {
		idx[i] = i
	}
	sort.SliceStable(idx, func(a, b int) bool { return keys[idx[a]] < keys[idx[b]] })
	out := make([]Route, len(routes))
	for i, j := range idx {
		out[i] = routes[j]
	}
	return out
}

func fill(r *Route, ds []int) {
	if len(ds) == 0 {
		return
	}
	bands := map[int]int{}
	for _, d := range ds {
		if d <= 5 {
			r.OnTime++
		}
		bands[int(math.Floor(float64(d)/5))*5]++
	}
	for start, n := range bands {
		r.Bands = append(r.Bands, Band{start, n})
	}
	slices.SortFunc(r.Bands, func(a, b Band) int { return a.Start - b.Start })
	s := slices.Clone(ds)
	slices.Sort(s)
	n := len(s)
	r.Worst = s[n-1]
	if n%2 == 1 {
		r.Median = float64(s[n/2])
	} else {
		r.Median = (float64(s[n/2-1]) + float64(s[n/2])) / 2
	}
}
