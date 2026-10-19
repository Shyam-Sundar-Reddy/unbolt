package generated

import (
	"fmt"
)


type CardData struct {
	CardNumber string
	CardExp int16
}

type CheckData struct {
	CheckNumber int64
	BankRouting int32
}

type PaymentRecord struct {
	PaymentType string
	PaymentAmount int64
	CardData CardData
	CheckData CheckData // REDEFINES CARD-DATA
}

func ValidatePaymentAmount(v int64) error {
	if v < -999999999 || v > 999999999 {
		return fmt.Errorf("PAYMENT-AMOUNT: %v outside -999999999..999999999", v)
	}
	return nil
}

func ValidateCardExp(v int16) error {
	if v < 0 || v > 9999 {
		return fmt.Errorf("CARD-EXP: %v outside 0..9999", v)
	}
	return nil
}

func ValidateCheckNumber(v int64) error {
	if v < 0 || v > 9999999999 {
		return fmt.Errorf("CHECK-NUMBER: %v outside 0..9999999999", v)
	}
	return nil
}

func ValidateBankRouting(v int32) error {
	if v < 0 || v > 999999999 {
		return fmt.Errorf("BANK-ROUTING: %v outside 0..999999999", v)
	}
	return nil
}
