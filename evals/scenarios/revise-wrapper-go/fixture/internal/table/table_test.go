package table

import "testing"

func TestRenderCountsRunes(t *testing.T) {
	got := Render([]string{"route", "sailings", "notes"}, []bool{false, true, false},
		[][]string{{"Inchmara–Dunvoan", "12", "ok"}, {"Kilbride–Eilean Rùm", "3", "-"}})
	want := "" +
		"route                sailings  notes\n" +
		"Inchmara–Dunvoan           12  ok\n" +
		"Kilbride–Eilean Rùm         3  -\n"
	if got != want {
		t.Errorf("got\n%s\nwant\n%s", got, want)
	}
}
