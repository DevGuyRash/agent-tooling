package forecast

import (
	"testing"

	"permitctl/internal/permits"
)

func TestTable(t *testing.T) {
	all, err := permits.Read("../../cmd/permitctl/testdata/permits.csv")
	if err != nil {
		t.Fatal(err)
	}
	want := "band  permits     income\n" +
		"A           2     114.00\n" +
		"B           1      58.00\n" +
		"C           0       0.00\n" +
		"D           1     172.00\n" +
		"E           1     188.00\n" +
		"F           1     316.00\n" +
		"total       6     848.00\n"
	if got := Table(all); got != want {
		t.Errorf("got\n%s\nwant\n%s", got, want)
	}
}
