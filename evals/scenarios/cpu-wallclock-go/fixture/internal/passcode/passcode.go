// Package passcode derives the check codes the turnstiles verify offline (docs/codes.md).
package passcode

import (
	"crypto/pbkdf2"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"strings"
)

// Iterations is the PBKDF2 work factor turnstile firmware 4.x verifies with. Changing it changes every
// code: the turnstiles would reject every pass until they are reflashed.
const Iterations = 300000

// Version is the derivation's label; it is part of every salt.
const Version = "gatepass/v2"

// codeBytes is how much of the derived key a code carries: 80 bits, 16 base32 characters.
const codeBytes = 10

// alphabet is Crockford's base32 (no I, L, O, U), which the gate staff can read aloud.
const alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

// Code is the check code for one issue of a pass at an event. Issue 0 is the pass as first sold; a
// reissued pass (lost, transferred) gets the next issue number and a new code, which retires the old one.
func Code(secret []byte, event, passID string, issue int) string {
	salt := fmt.Sprintf("%s:%s:%s:%d", Version, event, passID, issue)
	key, err := pbkdf2.Key(sha256.New, string(secret), []byte(salt), Iterations, codeBytes)
	if err != nil {
		panic(fmt.Sprintf("passcode: %v", err)) // only for parameters outside PBKDF2's range, which these are not
	}
	return format(key)
}

// format writes 80 bits as 16 base32 characters in groups of four: KQ7M-4XR2-PD8Z-J3WA.
func format(key []byte) string {
	var b strings.Builder
	var acc uint64
	bits := 0
	n := 0
	for _, c := range key {
		acc = acc<<8 | uint64(c)
		bits += 8
		for bits >= 5 {
			bits -= 5
			if n > 0 && n%4 == 0 {
				b.WriteByte('-')
			}
			b.WriteByte(alphabet[(acc>>uint(bits))&31])
			n++
		}
	}
	return b.String()
}

// LoadKey reads an event's secret: hex in a file, surrounding whitespace ignored, at least 16 bytes.
func LoadKey(path string) ([]byte, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	key, err := hex.DecodeString(strings.TrimSpace(string(data)))
	if err != nil {
		return nil, fmt.Errorf("%s: not a hex key: %v", path, err)
	}
	if len(key) < 16 {
		return nil, fmt.Errorf("%s: key is %d bytes, want at least 16", path, len(key))
	}
	return key, nil
}
