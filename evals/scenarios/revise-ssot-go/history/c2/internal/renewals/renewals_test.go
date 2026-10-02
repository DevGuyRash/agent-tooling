package renewals

import (
	"testing"
	"time"

	"permitctl/internal/permits"
)

func TestLetters(t *testing.T) {
	all, err := permits.Read("../../cmd/permitctl/testdata/permits.csv")
	if err != nil {
		t.Fatal(err)
	}
	got := Letters(all, time.Date(2027, 4, 1, 0, 0, 0, 0, time.UTC))
	want := "FV-10442 KX19 TRV (14 Orchard Row): band D, diesel, 172.00\n" +
		"FV-10451 LM21 OPA (14 Orchard Row): band A, second permit, 82.00\n" +
		"FV-10470 FG70 WSD (9 Larch Close): band B, 58.00\n" +
		"FV-10458 BD68 KQE (3 Weavers Yard): band A, 32.00\n" +
		"4 renewals due in 2027-04, 344.00 in total\n"
	if got != want {
		t.Errorf("got\n%s\nwant\n%s", got, want)
	}
}
