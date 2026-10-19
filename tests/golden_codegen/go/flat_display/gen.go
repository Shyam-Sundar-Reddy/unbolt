package generated

import (
	"fmt"
)


type CustomerRecord struct {
	CustomerId int32
	CustomerAge int16
	AccountBalance int64
}

func ValidateCustomerId(v int32) error {
	if v < 0 || v > 999999 {
		return fmt.Errorf("CUSTOMER-ID: %v outside 0..999999", v)
	}
	return nil
}

func ValidateCustomerAge(v int16) error {
	if v < -999 || v > 999 {
		return fmt.Errorf("CUSTOMER-AGE: %v outside -999..999", v)
	}
	return nil
}

func ValidateAccountBalance(v int64) error {
	if v < -999999999 || v > 999999999 {
		return fmt.Errorf("ACCOUNT-BALANCE: %v outside -999999999..999999999", v)
	}
	return nil
}
